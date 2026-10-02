from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

from runtime.phase3.trusted_runtime import (
    ControlFailure,
    IdentityClaims,
    TenantContext,
)
from runtime.phase4.prompt_injection import (
    PromptInjectionAssessment,
    PromptInjectionOutcome,
)
from runtime.phase4.tool_approval import (
    ApprovalContext,
    canonical_arguments_digest,
    verify_tool_approval,
)
from runtime.phase4.tool_audit import build_ai_audit_event, validate_ai_audit_event
from runtime.phase4.tool_governance import (
    GovernedToolInvocation,
    validate_and_govern_tool_invocation,
)
from runtime.phase4.tool_invocation import build_failure_response
from runtime.phase4.tool_policy import (
    PolicyOutcome,
    ToolPolicyDecision,
)
from runtime.phase4.tool_registry import (
    RegistryFailure,
    ToolMetadata,
    load_registry,
    validate_tool_metadata,
)


NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
HOSTILE_DETAIL = "hostile-secret-qualification-detail"
VALID_REQUEST = {
    "schema_version": 1,
    "request_id": "qualification-request-0001",
    "tool_id": "example_get_cash_position",
    "arguments": {"as_of_date": "2026-08-01"},
}


METADATA_SCHEMA_ID = (
    "https://portfolio.invalid/contracts/phase4/tool-metadata.schema.json"
)


def reject_schema_retrieval(uri: str):
    raise NoSuchResource(ref=uri)


def load_schema_validator(
    path: str,
    *,
    local_schemas: tuple[str, ...] = (),
) -> Draft202012Validator:
    schema = json.loads(Path(path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    registry = Registry(retrieve=reject_schema_retrieval)
    for local_path in local_schemas:
        local_schema = json.loads(Path(local_path).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(local_schema)
        schema_id = local_schema.get("$id")
        if schema_id != METADATA_SCHEMA_ID:
            raise AssertionError("unexpected local metadata schema ID")
        registry = registry.with_resource(
            schema_id,
            Resource.from_contents(local_schema),
        )
    return Draft202012Validator(schema, registry=registry)


RESPONSE_VALIDATOR = load_schema_validator(
    "contracts/phase4/tool-invocation-response.schema.json"
)
AUDIT_VALIDATOR = load_schema_validator("contracts/phase4/ai-audit-event.schema.json")
APPROVAL_VALIDATOR = load_schema_validator(
    "contracts/phase4/tool-approval-decision.schema.json"
)
REGISTRY_VALIDATOR = load_schema_validator(
    "contracts/phase4/tool-registry.schema.json",
    local_schemas=("contracts/phase4/tool-metadata.schema.json",),
)


def string_leaves(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        return tuple(
            leaf
            for key, item in value.items()
            for leaf in (*string_leaves(key), *string_leaves(item))
        )
    if isinstance(value, list):
        return tuple(leaf for item in value for leaf in string_leaves(item))
    return ()


class BoundaryRecorder:
    def __init__(self) -> None:
        self.sequence: list[str] = []
        self.approval_calls = 0
        self.audit_envelopes: list[dict[str, Any]] = []
        self.product_tool_calls = 0
        self.gateway_calls = 0
        self.provider_calls = 0


class ControlledAuthenticator:
    def __init__(self, recorder: BoundaryRecorder, mode: str) -> None:
        self.recorder = recorder
        self.mode = mode

    def authenticate(self, authorization: str) -> IdentityClaims:
        self.recorder.sequence.append("authentication")
        if self.mode == "timeout":
            raise TimeoutError(HOSTILE_DETAIL)
        if self.mode == "unavailable":
            raise RuntimeError(HOSTILE_DETAIL)
        if self.mode == "malformed":
            return IdentityClaims("", "", frozenset())
        if self.mode == "invalid" or authorization != "Bearer qualification-token":
            raise ControlFailure("authentication", "invalid_token")
        return IdentityClaims(
            "qualification-subject",
            "tenant-qualification",
            frozenset({"ai:invoke"}),
        )


class ControlledTenantResolver:
    def __init__(self, recorder: BoundaryRecorder, mode: str) -> None:
        self.recorder = recorder
        self.mode = mode

    def resolve(self, claims: IdentityClaims) -> TenantContext:
        self.recorder.sequence.append("tenant_context")
        if self.mode == "timeout":
            raise TimeoutError(HOSTILE_DETAIL)
        if self.mode == "unavailable":
            raise RuntimeError(HOSTILE_DETAIL)
        if self.mode == "malformed":
            return TenantContext("", "")
        tenant_ref = hashlib.sha256(claims.tenant_claim.encode("utf-8")).hexdigest()[:16]
        return TenantContext(claims.tenant_claim, tenant_ref)


class ControlledAuthorizer:
    def __init__(self, recorder: BoundaryRecorder, mode: str) -> None:
        self.recorder = recorder
        self.mode = mode

    def authorize(
        self,
        claims: IdentityClaims,
        tenant: TenantContext,
        action: str,
    ) -> bool:
        self.recorder.sequence.append("authorization")
        if self.mode == "timeout":
            raise TimeoutError(HOSTILE_DETAIL)
        if self.mode == "unavailable":
            raise RuntimeError(HOSTILE_DETAIL)
        return (
            self.mode != "deny"
            and claims.subject == "qualification-subject"
            and tenant.tenant_id == "tenant-qualification"
            and action == "example_get_cash_position.execute"
        )


class ControlledInjectionAssessor:
    def __init__(self, recorder: BoundaryRecorder, mode: str) -> None:
        self.recorder = recorder
        self.mode = mode

    def assess(self, arguments: dict[str, Any]) -> Any:
        self.recorder.sequence.append("prompt_injection_assessment")
        if self.mode == "timeout":
            raise TimeoutError(HOSTILE_DETAIL)
        if self.mode == "unavailable":
            raise RuntimeError(HOSTILE_DETAIL)
        if self.mode == "malformed":
            return {"outcome": "clear", "indicator_categories": []}
        if self.mode == "suspected":
            return PromptInjectionAssessment(
                PromptInjectionOutcome.SUSPECTED,
                ("instruction_override",),
            )
        if arguments != VALID_REQUEST["arguments"]:
            raise AssertionError("validated arguments were not preserved")
        return PromptInjectionAssessment(PromptInjectionOutcome.CLEAR, ())


class ControlledPolicyEngine:
    def __init__(self, recorder: BoundaryRecorder, mode: str) -> None:
        self.recorder = recorder
        self.mode = mode

    def evaluate(self, policy_input: Any) -> Any:
        self.recorder.sequence.append("agent_policy_engine")
        if self.mode == "timeout":
            raise TimeoutError(HOSTILE_DETAIL)
        if self.mode == "unavailable":
            raise RuntimeError(HOSTILE_DETAIL)
        if self.mode == "malformed":
            return {"outcome": "require_approval"}
        if self.mode == "deny":
            return ToolPolicyDecision(PolicyOutcome.DENY, "engine_denied")
        return ToolPolicyDecision(
            PolicyOutcome.REQUIRE_APPROVAL,
            "registry_requires_approval",
        )


class ControlledApprovalVerifier:
    def __init__(
        self,
        recorder: BoundaryRecorder,
        decision: dict[str, Any],
        mode: str,
    ) -> None:
        self.recorder = recorder
        self.decision = decision
        self.mode = mode

    def retrieve_verified(self, approval_id: str) -> Any:
        self.recorder.sequence.append("human_approval_verification")
        self.recorder.approval_calls += 1
        if self.mode == "timeout":
            raise TimeoutError(HOSTILE_DETAIL)
        if self.mode == "unavailable":
            raise RuntimeError(HOSTILE_DETAIL)
        return deepcopy(self.decision)


def approval_registry(*, enabled: bool = True) -> dict[str, ToolMetadata]:
    raw_registry = json.loads(
        Path("tests/phase4/registry/sample-registry.json").read_text(encoding="utf-8")
    )
    raw_tool = deepcopy(raw_registry["tools"][0])
    raw_tool["enabled"] = enabled
    raw_tool["risk_classification"] = "irreversible_high_impact"
    raw_tool["operation_type"] = "write"
    raw_tool["approval"] = {
        "required": True,
        "extension_point_ref": "phase-4c-human-approval-extension-point",
    }
    raw_tool["audit_classification"] = "high_sensitivity"
    tool = validate_tool_metadata(raw_tool)
    return {tool.id: tool}


def valid_approval_decision() -> dict[str, Any]:
    tenant_ref = hashlib.sha256(b"tenant-qualification").hexdigest()[:16]
    subject_ref = hashlib.sha256(b"qualification-subject").hexdigest()[:16]
    arguments_digest = canonical_arguments_digest(VALID_REQUEST["arguments"])
    return {
        "schema_version": 1,
        "approval_id": "approval-qualification-0001",
        "decision": "approved",
        "request_id": VALID_REQUEST["request_id"],
        "tenant_ref": tenant_ref,
        "subject_ref": subject_ref,
        "tool_id": VALID_REQUEST["tool_id"],
        "tool_version": "0.1.0",
        "required_action": "example_get_cash_position.execute",
        "risk_classification": "irreversible_high_impact",
        "arguments_digest": arguments_digest,
        "issued_at": "2026-08-15T11:00:00Z",
        "expires_at": "2026-08-15T13:00:00Z",
        "consumed": False,
    }


def qualify(recorder: BoundaryRecorder) -> GovernedToolInvocation:
    return validate_and_govern_tool_invocation(
        ControlledAuthenticator(recorder, "ok"),
        ControlledTenantResolver(recorder, "ok"),
        ControlledAuthorizer(recorder, "ok"),
        ControlledInjectionAssessor(recorder, "clear"),
        ControlledPolicyEngine(recorder, "approval"),
        ControlledApprovalVerifier(recorder, valid_approval_decision(), "ok"),
        approval_registry(),
        "Bearer qualification-token",
        deepcopy(VALID_REQUEST),
        "approval-qualification-0001",
        now=NOW,
    )


def build_qualified_audit(governed: GovernedToolInvocation) -> dict[str, Any]:
    return build_ai_audit_event(
        event_id="qualification-event-0001",
        occurred_at=NOW,
        request_id=governed.request_id,
        tenant_ref=governed.tenant.tenant_ref,
        subject_ref=governed.subject_ref,
        tool_id=governed.tool.id,
        tool_version=governed.tool.version,
        required_action=governed.tool.authorization.required_action,
        risk_classification=governed.tool.risk_classification.value,
        authorization_result="allowed",
        injection_result="clear",
        indicator_categories=(),
        policy_outcome=governed.policy_outcome,
        policy_reason_code=governed.policy_reason_code,
        approval_result="approved",
        governance_result="qualified",
        failure=None,
    )


class FailureBoundaryTests(unittest.TestCase):
    def invoke_rejected(
        self,
        *,
        authentication: str = "ok",
        tenant: str = "ok",
        authorization: str = "ok",
        registry_state: str = "ready",
        body: dict[str, Any] | None = None,
        injection: str = "clear",
        policy: str = "approval",
        approval: str = "ok",
        approval_id: str | None = "approval-qualification-0001",
        decision: dict[str, Any] | None = None,
    ) -> tuple[ControlFailure, BoundaryRecorder, dict[str, Any]]:
        recorder = BoundaryRecorder()
        registry = approval_registry(enabled=registry_state != "disabled")
        request = deepcopy(body if body is not None else VALID_REQUEST)
        verifier = ControlledApprovalVerifier(
            recorder,
            decision if decision is not None else valid_approval_decision(),
            approval,
        )
        with self.assertRaises(ControlFailure) as raised:
            validate_and_govern_tool_invocation(
                ControlledAuthenticator(recorder, authentication),
                ControlledTenantResolver(recorder, tenant),
                ControlledAuthorizer(recorder, authorization),
                ControlledInjectionAssessor(recorder, injection),
                ControlledPolicyEngine(recorder, policy),
                verifier,
                registry,
                "Bearer qualification-token",
                request,
                approval_id,
                now=NOW,
            )
        failure = raised.exception
        response = build_failure_response(
            request.get("request_id"),
            request.get("tool_id"),
            failure,
        )
        self.assertTrue(RESPONSE_VALIDATOR.is_valid(response))
        serialized = json.dumps(response, sort_keys=True)
        self.assertNotIn(HOSTILE_DETAIL, serialized)
        for untrusted_value in string_leaves(request.get("arguments")):
            self.assertNotIn(untrusted_value, serialized)
        self.assertEqual(recorder.product_tool_calls, 0)
        self.assertEqual(recorder.gateway_calls, 0)
        self.assertEqual(recorder.provider_calls, 0)
        return failure, recorder, response

    def test_each_control_and_dependency_failure_stops_immediately(self):
        cases = (
            (
                "authentication-invalid",
                {"authentication": "invalid"},
                ("authentication", "invalid_token"),
                ["authentication"],
            ),
            (
                "authentication-dependency",
                {"authentication": "unavailable"},
                ("authentication", "unavailable"),
                ["authentication"],
            ),
            (
                "tenant-malformed",
                {"tenant": "malformed"},
                ("tenant_context", "malformed_context"),
                ["authentication", "tenant_context"],
            ),
            (
                "tenant-dependency",
                {"tenant": "timeout"},
                ("tenant_context", "timeout"),
                ["authentication", "tenant_context"],
            ),
            (
                "authorization-denied",
                {"authorization": "deny"},
                ("authorization", "denied"),
                ["authentication", "tenant_context", "authorization"],
            ),
            (
                "authorization-dependency",
                {"authorization": "unavailable"},
                ("authorization", "unavailable"),
                ["authentication", "tenant_context", "authorization"],
            ),
            (
                "registry-unknown",
                {"body": {**VALID_REQUEST, "tool_id": "unknown_qualification_tool"}},
                ("structured_input_validation", "unknown_tool"),
                ["authentication", "tenant_context"],
            ),
            (
                "registry-disabled",
                {"registry_state": "disabled"},
                ("structured_input_validation", "disabled_tool"),
                ["authentication", "tenant_context", "authorization"],
            ),
            (
                "arguments-invalid",
                {
                    "body": {
                        **VALID_REQUEST,
                        "arguments": {"as_of_date": "hostile-invalid-date"},
                    }
                },
                ("structured_input_validation", "argument_schema_mismatch"),
                ["authentication", "tenant_context", "authorization"],
            ),
            (
                "injection-suspected",
                {"injection": "suspected"},
                ("prompt_injection_assessment", "suspected_injection"),
                [
                    "authentication",
                    "tenant_context",
                    "authorization",
                    "prompt_injection_assessment",
                ],
            ),
            (
                "injection-malformed",
                {"injection": "malformed"},
                ("prompt_injection_assessment", "malformed_assessment"),
                [
                    "authentication",
                    "tenant_context",
                    "authorization",
                    "prompt_injection_assessment",
                ],
            ),
            (
                "injection-dependency",
                {"injection": "unavailable"},
                ("prompt_injection_assessment", "unavailable"),
                [
                    "authentication",
                    "tenant_context",
                    "authorization",
                    "prompt_injection_assessment",
                ],
            ),
            (
                "policy-denied",
                {"policy": "deny"},
                ("agent_policy_engine", "denied"),
                [
                    "authentication",
                    "tenant_context",
                    "authorization",
                    "prompt_injection_assessment",
                    "agent_policy_engine",
                ],
            ),
            (
                "policy-malformed",
                {"policy": "malformed"},
                ("agent_policy_engine", "malformed_decision"),
                [
                    "authentication",
                    "tenant_context",
                    "authorization",
                    "prompt_injection_assessment",
                    "agent_policy_engine",
                ],
            ),
            (
                "policy-dependency",
                {"policy": "timeout"},
                ("agent_policy_engine", "timeout"),
                [
                    "authentication",
                    "tenant_context",
                    "authorization",
                    "prompt_injection_assessment",
                    "agent_policy_engine",
                ],
            ),
            (
                "approval-missing",
                {"approval_id": None},
                ("human_approval_verification", "missing_decision"),
                [
                    "authentication",
                    "tenant_context",
                    "authorization",
                    "prompt_injection_assessment",
                    "agent_policy_engine",
                ],
            ),
            (
                "approval-invalid-id",
                {"approval_id": "bad id"},
                ("human_approval_verification", "missing_decision"),
                [
                    "authentication",
                    "tenant_context",
                    "authorization",
                    "prompt_injection_assessment",
                    "agent_policy_engine",
                ],
            ),
            (
                "approval-dependency",
                {"approval": "unavailable"},
                ("human_approval_verification", "unavailable"),
                [
                    "authentication",
                    "tenant_context",
                    "authorization",
                    "prompt_injection_assessment",
                    "agent_policy_engine",
                    "human_approval_verification",
                ],
            ),
        )
        for case_id, options, expected_failure, expected_sequence in cases:
            with self.subTest(case_id=case_id):
                failure, recorder, _response = self.invoke_rejected(**options)
                self.assertEqual(
                    (failure.stage, failure.category),
                    expected_failure,
                )
                self.assertEqual(recorder.sequence, expected_sequence)
                if case_id in {"approval-missing", "approval-invalid-id"}:
                    self.assertEqual(recorder.approval_calls, 0)

    def test_approval_binding_and_state_abuse_fails_closed(self):
        # The consumed case proves rejection only when the verifier reports an
        # already-consumed decision. It intentionally makes no atomic consume,
        # replay-race, or concurrency-resistance claim.
        mutations = (
            (
                "approval-id",
                {"approval_id": "approval-qualification-9999"},
                "malformed_decision",
            ),
            ("tenant", {"tenant_ref": "0" * 16}, "tenant_mismatch"),
            ("user", {"subject_ref": "0" * 16}, "subject_mismatch"),
            (
                "request",
                {"request_id": "qualification-request-9999"},
                "tool_mismatch",
            ),
            ("tool", {"tool_id": "different_tool"}, "tool_mismatch"),
            (
                "arguments",
                {"arguments_digest": "0" * 64},
                "arguments_digest_mismatch",
            ),
            ("consumed", {"consumed": True}, "replayed_decision"),
            ("denied", {"decision": "denied"}, "denied_decision"),
            (
                "expired",
                {"expires_at": "2026-08-15T11:59:59Z"},
                "expired_decision",
            ),
        )
        for case_id, mutation, expected_category in mutations:
            with self.subTest(case_id=case_id):
                decision = {**valid_approval_decision(), **mutation}
                failure, recorder, _response = self.invoke_rejected(decision=decision)
                self.assertEqual(
                    (failure.stage, failure.category),
                    ("human_approval_verification", expected_category),
                )
                self.assertEqual(recorder.approval_calls, 1)
                self.assertEqual(
                    recorder.sequence[-1],
                    "human_approval_verification",
                )

    def test_governance_success_is_qualification_only_and_audit_is_sanitized(self):
        recorder = BoundaryRecorder()
        governed = validate_and_govern_tool_invocation(
            ControlledAuthenticator(recorder, "ok"),
            ControlledTenantResolver(recorder, "ok"),
            ControlledAuthorizer(recorder, "ok"),
            ControlledInjectionAssessor(recorder, "clear"),
            ControlledPolicyEngine(recorder, "approval"),
            ControlledApprovalVerifier(recorder, valid_approval_decision(), "ok"),
            approval_registry(),
            "Bearer qualification-token",
            deepcopy(VALID_REQUEST),
            "approval-qualification-0001",
            now=NOW,
        )
        self.assertIsInstance(governed, GovernedToolInvocation)
        event = build_qualified_audit(governed)
        recorder.audit_envelopes.append(event)
        self.assertTrue(AUDIT_VALIDATOR.is_valid(event))
        serialized = json.dumps(event, sort_keys=True)
        self.assertNotIn(VALID_REQUEST["arguments"]["as_of_date"], serialized)
        self.assertNotIn("arguments", serialized)
        self.assertEqual(recorder.product_tool_calls, 0)
        self.assertEqual(recorder.gateway_calls, 0)
        self.assertEqual(recorder.provider_calls, 0)

    def test_audit_failure_stops_before_any_execution(self):
        recorder = BoundaryRecorder()
        governed = qualify(recorder)
        recorder.sequence.append("audit")
        invalid_event_id = "invalid/event-id"
        with self.assertRaises(ControlFailure) as raised:
            build_ai_audit_event(
                event_id=invalid_event_id,
                occurred_at=NOW,
                request_id=governed.request_id,
                tenant_ref=governed.tenant.tenant_ref,
                subject_ref=governed.subject_ref,
                tool_id=governed.tool.id,
                tool_version=governed.tool.version,
                required_action=governed.tool.authorization.required_action,
                risk_classification=governed.tool.risk_classification.value,
                authorization_result="allowed",
                injection_result="clear",
                indicator_categories=(),
                policy_outcome=governed.policy_outcome,
                policy_reason_code=governed.policy_reason_code,
                approval_result="approved",
                governance_result="qualified",
                failure=None,
            )
        self.assertEqual(
            (raised.exception.stage, raised.exception.category),
            ("audit", "invalid_event"),
        )
        response = build_failure_response(
            governed.request_id,
            governed.tool.id,
            raised.exception,
        )
        self.assertTrue(RESPONSE_VALIDATOR.is_valid(response))
        self.assertNotIn(invalid_event_id, json.dumps(response, sort_keys=True))
        self.assertEqual(recorder.audit_envelopes, [])
        self.assertEqual(recorder.product_tool_calls, 0)
        self.assertEqual(recorder.gateway_calls, 0)
        self.assertEqual(recorder.provider_calls, 0)

    def test_hostile_failure_identifiers_are_sanitized_and_not_echoed(self):
        response = build_failure_response(
            HOSTILE_DETAIL + "/request",
            HOSTILE_DETAIL + "/tool",
            ControlFailure("untrusted-stage", HOSTILE_DETAIL),
        )
        self.assertTrue(RESPONSE_VALIDATOR.is_valid(response))
        self.assertIsNone(response["request_id"])
        self.assertIsNone(response["tool_id"])
        self.assertNotIn(HOSTILE_DETAIL, json.dumps(response, sort_keys=True))

class BooleanVersionTests(unittest.TestCase):
    def test_registry_rejects_boolean_schema_version(self):
        registry = json.loads(
            Path("tests/phase4/registry/sample-registry.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(REGISTRY_VALIDATOR.is_valid(registry))
        registry["schema_version"] = True
        self.assertFalse(REGISTRY_VALIDATOR.is_valid(registry))
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaises(RegistryFailure) as raised:
                load_registry(path)
        self.assertEqual(raised.exception.category, "malformed_metadata")

    def test_approval_rejects_boolean_schema_version(self):
        recorder = BoundaryRecorder()
        decision = {**valid_approval_decision(), "schema_version": True}
        self.assertFalse(APPROVAL_VALIDATOR.is_valid(decision))
        verifier = ControlledApprovalVerifier(recorder, decision, "ok")
        context = ApprovalContext(
            request_id=VALID_REQUEST["request_id"],
            tenant_ref=decision["tenant_ref"],
            subject_ref=decision["subject_ref"],
            tool_id=VALID_REQUEST["tool_id"],
            tool_version="0.1.0",
            required_action="example_get_cash_position.execute",
            risk_classification="irreversible_high_impact",
            arguments_digest=valid_approval_decision()["arguments_digest"],
        )
        with self.assertRaises(ControlFailure) as raised:
            verify_tool_approval(
                verifier,
                "approval-qualification-0001",
                context,
                now=NOW,
            )
        self.assertEqual(
            (raised.exception.stage, raised.exception.category),
            ("human_approval_verification", "malformed_decision"),
        )

    def test_audit_rejects_boolean_schema_version(self):
        recorder = BoundaryRecorder()
        governed = qualify(recorder)
        event = build_qualified_audit(governed)
        self.assertTrue(AUDIT_VALIDATOR.is_valid(event))
        invalid = {**event, "schema_version": True}
        self.assertFalse(AUDIT_VALIDATOR.is_valid(invalid))
        with self.assertRaises(ControlFailure) as raised:
            validate_ai_audit_event(invalid)
        self.assertEqual(
            (raised.exception.stage, raised.exception.category),
            ("audit", "invalid_event"),
        )


if __name__ == "__main__":
    unittest.main()
