import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from runtime.phase3.mocks import MockAuthenticator, MockTenantResolver, Recorder
from runtime.phase3.trusted_runtime import ControlFailure, IdentityClaims, TenantContext
from runtime.phase4.prompt_injection import PromptInjectionAssessment, PromptInjectionOutcome
from runtime.phase4.tool_governance import validate_and_govern_tool_invocation
from runtime.phase4.tool_invocation import (
    ALLOWED_STAGE_CATEGORIES,
    ARGUMENT_VALIDATORS,
    FALLBACK_CATEGORY,
    FALLBACK_STAGE,
    build_failure_response,
    build_validated_success_response,
    validate_example_get_cash_position_output,
    validate_invocation_envelope,
    validate_tool_invocation,
)
from runtime.phase4.tool_policy import PolicyOutcome, ToolPolicyDecision
from runtime.phase4.tool_registry import load_registry, validate_tool_metadata

VALID_REQUEST = {
    "schema_version": 1,
    "request_id": "qualification-request-0001",
    "tool_id": "example_get_cash_position",
    "arguments": {"as_of_date": "2026-08-01"},
}
VALID_TENANT_REFS = (
    "9f31a8c247bd10e6",
    "0000000000000000",
    "abcdef0123456789",
)
INVALID_TENANT_REFS = (
    ("empty", ""),
    ("whitespace", "   "),
    ("short", "abcdef012345678"),
    ("long", "abcdef01234567890"),
    ("uppercase", "ABCDEF0123456789"),
    ("nonhex", "ghijkl0123456789"),
    ("hyphen", "abcdef01-2345678"),
    ("underscore", "abcdef01_2345678"),
    ("internal space", "abcdef01 2345678"),
    ("tenant name", "demo-tenant"),
    ("email", "demo@example.invalid"),
    ("uuid", "00000000-0000-4000-8000-000000000000"),
    ("numeric organization id", "123456"),
    ("account shaped", "acct_demo_001"),
    ("customer shaped", "customer_demo_001"),
    ("leading space", " abcdef0123456789"),
    ("trailing space", "abcdef0123456789 "),
    ("null", None),
    ("integer", 123456),
)


class FixedTenantResolver:
    def __init__(self, recorder: Recorder, tenant_ref):
        self.recorder, self.tenant_ref = recorder, tenant_ref

    def resolve(self, claims: IdentityClaims) -> TenantContext:
        self.recorder.sequence.append("tenant_context")
        return TenantContext(claims.tenant_claim, self.tenant_ref)


class MockToolAuthorizer:
    """Authorizes based only on scope; records every action it is called
    with, so tests can prove authorization is driven by the registry, never
    by request content."""

    def __init__(self, recorder: Recorder, mode: str = "ok"):
        self.recorder, self.mode = recorder, mode
        self.seen_actions: list[str] = []

    def authorize(self, claims: IdentityClaims, tenant: TenantContext, action: str) -> bool:
        self.recorder.sequence.append("authorization")
        self.seen_actions.append(action)
        return self.mode != "deny" and "ai:invoke" in claims.scopes


def build_deps(mode: str = "ok"):
    recorder = Recorder()
    return (
        MockAuthenticator(recorder, "ok"),
        MockTenantResolver(recorder, "ok"),
        MockToolAuthorizer(recorder, mode),
        recorder,
    )


def registry_with(mutation) -> dict:
    raw = json.loads(Path("tests/phase4/registry/sample-registry.json").read_text())
    mutation(raw)
    return {entry["id"]: validate_tool_metadata(entry) for entry in raw["tools"]}


class InvocationEnvelopeTests(unittest.TestCase):
    def test_valid_envelope_accepted(self):
        request_id, tool_id, arguments = validate_invocation_envelope(VALID_REQUEST)
        self.assertEqual((request_id, tool_id), ("qualification-request-0001", "example_get_cash_position"))

    def test_tenant_id_at_top_level_rejected(self):
        body = {**deepcopy(VALID_REQUEST), "tenant_id": "attacker-controlled"}
        with self.assertRaises(ControlFailure) as ctx:
            validate_invocation_envelope(body)
        self.assertEqual((ctx.exception.stage, ctx.exception.category), ("structured_input_validation", "invalid_request"))

    def test_tenant_shaped_key_nested_in_dict_rejected(self):
        body = deepcopy(VALID_REQUEST)
        body["arguments"] = {"as_of_date": "2026-08-01", "context": {"tenant": {"id": "x"}}}
        with self.assertRaises(ControlFailure) as ctx:
            validate_invocation_envelope(body)
        self.assertEqual(ctx.exception.category, "invalid_request")

    def test_tenant_shaped_key_nested_in_list_rejected(self):
        body = deepcopy(VALID_REQUEST)
        body["arguments"] = {"items": [{"note": "ok"}, {"tenant_id": "x"}]}
        with self.assertRaises(ControlFailure) as ctx:
            validate_invocation_envelope(body)
        self.assertEqual(ctx.exception.category, "invalid_request")

    def test_unrelated_word_containing_tenant_substring_not_rejected(self):
        # "tenants_report" normalizes to "tenants-report", which is not in
        # TENANT_SHAPED_KEYS -- envelope validation (which does not apply a
        # tool's argument-content schema) must accept it. Proves the
        # recursive check uses exact normalized-key matching, not broad
        # substring matching.
        body = deepcopy(VALID_REQUEST)
        body["arguments"] = {"as_of_date": "2026-08-01", "tenants_report": True}
        request_id, tool_id, arguments = validate_invocation_envelope(body)
        self.assertEqual(arguments, {"as_of_date": "2026-08-01", "tenants_report": True})

    def test_additional_property_rejected(self):
        body = {**deepcopy(VALID_REQUEST), "extra": "field"}
        with self.assertRaises(ControlFailure) as ctx:
            validate_invocation_envelope(body)
        self.assertEqual(ctx.exception.category, "invalid_request")

    def test_malformed_request_not_a_dict_rejected(self):
        with self.assertRaises(ControlFailure) as ctx:
            validate_invocation_envelope("not a dict")
        self.assertEqual(ctx.exception.category, "invalid_request")


class ArgumentAndOutputSchemaTests(unittest.TestCase):
    def test_valid_arguments_accepted(self):
        result = ARGUMENT_VALIDATORS["example_get_cash_position"]({"as_of_date": "2026-08-01"})
        self.assertEqual(result, {"as_of_date": "2026-08-01"})

    def test_arguments_failing_input_schema_rejected(self):
        with self.assertRaises(ControlFailure) as ctx:
            ARGUMENT_VALIDATORS["example_get_cash_position"]({"as_of_date": "not-a-date"})
        self.assertEqual((ctx.exception.stage, ctx.exception.category), ("structured_input_validation", "argument_schema_mismatch"))

    def test_output_failing_schema_rejected(self):
        with self.assertRaises(ControlFailure) as ctx:
            validate_example_get_cash_position_output({"as_of_date": "2026-08-01", "cash_position_minor_units": 1.5, "currency": "SAR"})
        self.assertEqual((ctx.exception.stage, ctx.exception.category), ("structured_output_validation", "output_schema_mismatch"))


class SuccessResponseValidationTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry("tests/phase4/registry/sample-registry.json")
        self.tool = self.registry["example_get_cash_position"]

    def test_valid_output_produces_success_envelope(self):
        raw_result = {"as_of_date": "2026-08-01", "cash_position_minor_units": 100, "currency": "SAR"}
        response = build_validated_success_response("qualification-request-0001", self.tool, raw_result)
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["result"], raw_result)

    def test_invalid_output_cannot_produce_success_envelope(self):
        with self.assertRaises(ControlFailure) as ctx:
            build_validated_success_response("qualification-request-0001", self.tool, {"currency": "SAR"})
        self.assertEqual((ctx.exception.stage, ctx.exception.category), ("structured_output_validation", "output_schema_mismatch"))

    def test_missing_output_validator_fails_closed(self):
        write_tool = self.registry["example_void_invoice"]
        with self.assertRaises(ControlFailure) as ctx:
            build_validated_success_response("qualification-request-0001", write_tool, {"anything": "goes"})
        self.assertEqual(ctx.exception.category, "output_schema_mismatch")

    def test_response_result_is_the_validated_result(self):
        raw_result = {"as_of_date": "2026-08-01", "cash_position_minor_units": 100, "currency": "SAR"}
        response = build_validated_success_response("qualification-request-0001", self.tool, raw_result)
        self.assertEqual(response["result"], raw_result)
        self.assertIsNot(response["result"], raw_result)


class FailureResponseVocabularyTests(unittest.TestCase):
    def test_known_stage_category_preserved(self):
        response = build_failure_response("id", "tool", ControlFailure("authorization", "denied"))
        self.assertEqual(response["error"], {"stage": "authorization", "category": "denied"})

    def test_unknown_stage_normalized(self):
        response = build_failure_response("id", "tool", ControlFailure("made_up_stage", "denied"))
        self.assertEqual(response["error"], {"stage": FALLBACK_STAGE, "category": FALLBACK_CATEGORY})

    def test_unknown_category_normalized(self):
        response = build_failure_response("id", "tool", ControlFailure("authentication", "made_up_category"))
        self.assertEqual(response["error"], {"stage": FALLBACK_STAGE, "category": FALLBACK_CATEGORY})

    def test_valid_category_wrong_stage_normalized(self):
        # "denied" is only valid under authorization, not structured_input_validation.
        response = build_failure_response("id", "tool", ControlFailure("structured_input_validation", "denied"))
        self.assertEqual(response["error"], {"stage": FALLBACK_STAGE, "category": FALLBACK_CATEGORY})

    def test_arbitrary_exception_text_never_echoed(self):
        failure = ControlFailure("authentication", "leaked-secret-value-should-not-appear")
        response = build_failure_response("qualification-request-0001", "example_get_cash_position", failure)
        serialized = json.dumps(response)
        self.assertNotIn("leaked-secret-value-should-not-appear", serialized)
        self.assertEqual(response["error"], {"stage": FALLBACK_STAGE, "category": FALLBACK_CATEGORY})

    def test_phase4c_stage_names_and_categories_are_exact(self):
        self.assertEqual(
            set(ALLOWED_STAGE_CATEGORIES["prompt_injection_assessment"]),
            {"timeout", "unavailable", "malformed_assessment", "unsupported_indicator_category", "suspected_injection"},
        )
        self.assertEqual(
            set(ALLOWED_STAGE_CATEGORIES["agent_policy_engine"]),
            {"timeout", "unavailable", "denied", "malformed_decision", "argument_digest_failure"},
        )
        self.assertEqual(
            set(ALLOWED_STAGE_CATEGORIES["human_approval_verification"]),
            {"timeout", "unavailable", "missing_decision", "denied_decision", "expired_decision", "replayed_decision", "tenant_mismatch", "subject_mismatch", "tool_mismatch", "arguments_digest_mismatch", "malformed_decision"},
        )

    def test_known_phase4c_failure_preserved(self):
        response = build_failure_response(
            "qualification-request-0001", "example_get_cash_position",
            ControlFailure("prompt_injection_assessment", "suspected_injection"),
        )
        self.assertEqual(
            response["error"],
            {"stage": "prompt_injection_assessment", "category": "suspected_injection"},
        )

    def test_phase4c_category_on_wrong_stage_normalized(self):
        response = build_failure_response(
            "qualification-request-0001", "example_get_cash_position",
            ControlFailure("agent_policy_engine", "missing_decision"),
        )
        self.assertEqual(
            response["error"],
            {"stage": FALLBACK_STAGE, "category": FALLBACK_CATEGORY},
        )


class ToolInvocationCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry("tests/phase4/registry/sample-registry.json")

    def test_valid_tenant_references_pass_unchanged_into_governance(self):
        for tenant_ref in VALID_TENANT_REFS:
            with self.subTest(tenant_ref=tenant_ref):
                authenticator, _, authorizer, recorder = build_deps()
                resolver = FixedTenantResolver(recorder, tenant_ref)
                invocation = validate_tool_invocation(
                    authenticator, resolver, authorizer, self.registry,
                    "Bearer qualification-token", VALID_REQUEST,
                )
                self.assertEqual(invocation.tenant.tenant_ref, tenant_ref)

                assessor = Mock()
                assessor.assess.return_value = PromptInjectionAssessment(
                    PromptInjectionOutcome.CLEAR, ()
                )
                policy = Mock()
                policy.evaluate.return_value = ToolPolicyDecision(
                    PolicyOutcome.ALLOW, "engine_allowed"
                )
                verifier = Mock()
                governed = validate_and_govern_tool_invocation(
                    authenticator, resolver, authorizer, assessor, policy,
                    verifier, self.registry, "Bearer qualification-token",
                    VALID_REQUEST, None,
                    now=datetime(2026, 8, 15, tzinfo=timezone.utc),
                )
                self.assertEqual(governed.tenant.tenant_ref, tenant_ref)
                self.assertEqual(policy.evaluate.call_args.args[0].tenant_ref, tenant_ref)
                self.assertEqual(policy.evaluate.call_count, 1)
                verifier.retrieve_verified.assert_not_called()

    def test_invalid_tenant_references_block_before_tool_or_governance(self):
        for case, tenant_ref in INVALID_TENANT_REFS:
            with self.subTest(case=case):
                authenticator, _, authorizer, recorder = build_deps()
                resolver = FixedTenantResolver(recorder, tenant_ref)
                with self.assertRaises(ControlFailure) as raised:
                    validate_tool_invocation(
                        authenticator, resolver, authorizer, self.registry,
                        "Bearer qualification-token", VALID_REQUEST,
                    )
                self.assertEqual(
                    (raised.exception.stage, raised.exception.category),
                    ("tenant_context", "malformed_context"),
                )
                self.assertEqual(str(raised.exception), "tenant_context:malformed_context")
                self.assertEqual(recorder.sequence, ["authentication", "tenant_context"])
                self.assertEqual(authorizer.seen_actions, [])

                authenticator, _, authorizer, recorder = build_deps()
                resolver = FixedTenantResolver(recorder, tenant_ref)
                assessor, policy, verifier = Mock(), Mock(), Mock()
                with self.assertRaises(ControlFailure) as governed_failure:
                    validate_and_govern_tool_invocation(
                        authenticator, resolver, authorizer, assessor, policy,
                        verifier, self.registry, "Bearer qualification-token",
                        VALID_REQUEST, None,
                        now=datetime(2026, 8, 15, tzinfo=timezone.utc),
                    )
                self.assertEqual(
                    (governed_failure.exception.stage, governed_failure.exception.category),
                    ("tenant_context", "malformed_context"),
                )
                self.assertEqual(str(governed_failure.exception), "tenant_context:malformed_context")
                self.assertEqual(recorder.sequence, ["authentication", "tenant_context"])
                self.assertEqual(authorizer.seen_actions, [])
                assessor.assess.assert_not_called()
                policy.evaluate.assert_not_called()
                verifier.retrieve_verified.assert_not_called()
                if isinstance(tenant_ref, str) and tenant_ref:
                    self.assertFalse(tenant_ref in str(raised.exception))
                    self.assertFalse(tenant_ref in str(governed_failure.exception))

    def test_valid_invocation_resolves(self):
        authenticator, tenant_resolver, authorizer, _ = build_deps()
        result = validate_tool_invocation(authenticator, tenant_resolver, authorizer, self.registry, "Bearer qualification-token", VALID_REQUEST)
        self.assertEqual(result.tool.id, "example_get_cash_position")

    def test_authorization_uses_registry_action_not_request(self):
        authenticator, tenant_resolver, authorizer, _ = build_deps()
        validate_tool_invocation(authenticator, tenant_resolver, authorizer, self.registry, "Bearer qualification-token", VALID_REQUEST)
        self.assertEqual(authorizer.seen_actions, ["example_get_cash_position.execute"])

    def test_unknown_tool_rejected(self):
        authenticator, tenant_resolver, authorizer, _ = build_deps()
        body = {**deepcopy(VALID_REQUEST), "tool_id": "does_not_exist"}
        with self.assertRaises(ControlFailure) as ctx:
            validate_tool_invocation(authenticator, tenant_resolver, authorizer, self.registry, "Bearer qualification-token", body)
        self.assertEqual((ctx.exception.stage, ctx.exception.category), ("structured_input_validation", "unknown_tool"))

    def test_disabled_tool_rejected(self):
        registry = registry_with(lambda raw: [
            entry.update(enabled=False) for entry in raw["tools"] if entry["id"] == "example_get_cash_position"
        ])
        authenticator, tenant_resolver, authorizer, _ = build_deps()
        with self.assertRaises(ControlFailure) as ctx:
            validate_tool_invocation(authenticator, tenant_resolver, authorizer, registry, "Bearer qualification-token", VALID_REQUEST)
        self.assertEqual(ctx.exception.category, "disabled_tool")

    def test_authorization_checked_before_registry_precondition_gate(self):
        # Disabled tool + unauthorized caller: must fail with "denied"
        # (authorization), never "disabled_tool" -- the registry gate must
        # not run, and must not leak the tool's enabled state, before
        # Authorization succeeds.
        registry = registry_with(lambda raw: [
            entry.update(enabled=False) for entry in raw["tools"] if entry["id"] == "example_get_cash_position"
        ])
        authenticator, tenant_resolver, authorizer, recorder = build_deps(mode="deny")
        with self.assertRaises(ControlFailure) as ctx:
            validate_tool_invocation(authenticator, tenant_resolver, authorizer, registry, "Bearer qualification-token", VALID_REQUEST)
        self.assertEqual((ctx.exception.stage, ctx.exception.category), ("authorization", "denied"))
        self.assertEqual(recorder.sequence, ["authentication", "tenant_context", "authorization"])

    def test_disabled_tool_rejected_only_after_authorization_succeeds(self):
        registry = registry_with(lambda raw: [
            entry.update(enabled=False) for entry in raw["tools"] if entry["id"] == "example_get_cash_position"
        ])
        authenticator, tenant_resolver, authorizer, recorder = build_deps(mode="ok")
        with self.assertRaises(ControlFailure) as ctx:
            validate_tool_invocation(authenticator, tenant_resolver, authorizer, registry, "Bearer qualification-token", VALID_REQUEST)
        self.assertEqual(ctx.exception.category, "disabled_tool")
        self.assertEqual(recorder.sequence, ["authentication", "tenant_context", "authorization"])

    def test_write_tool_with_deferred_schema_rejected(self):
        authenticator, tenant_resolver, authorizer, _ = build_deps()
        body = {**deepcopy(VALID_REQUEST), "tool_id": "example_edit_draft_invoice", "arguments": {}}
        with self.assertRaises(ControlFailure) as ctx:
            validate_tool_invocation(authenticator, tenant_resolver, authorizer, self.registry, "Bearer qualification-token", body)
        self.assertEqual(ctx.exception.category, "schema_deferred")

    def test_approval_required_write_remains_blocked(self):
        authenticator, tenant_resolver, authorizer, _ = build_deps()
        body = {**deepcopy(VALID_REQUEST), "tool_id": "example_void_invoice", "arguments": {}}
        with self.assertRaises(ControlFailure) as ctx:
            validate_tool_invocation(authenticator, tenant_resolver, authorizer, self.registry, "Bearer qualification-token", body)
        self.assertIn(ctx.exception.category, ("schema_deferred", "approval_required_no_decision"))

    def test_arguments_failing_schema_rejected_end_to_end(self):
        authenticator, tenant_resolver, authorizer, _ = build_deps()
        body = {**deepcopy(VALID_REQUEST), "arguments": {"as_of_date": "not-a-date"}}
        with self.assertRaises(ControlFailure) as ctx:
            validate_tool_invocation(authenticator, tenant_resolver, authorizer, self.registry, "Bearer qualification-token", body)
        self.assertEqual(ctx.exception.category, "argument_schema_mismatch")


if __name__ == "__main__":
    unittest.main()
