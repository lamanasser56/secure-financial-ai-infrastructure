import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from runtime.phase3.mocks import MockGateway, build_mock_runtime
from runtime.phase3.trusted_runtime import ControlFailure, STAGES, TenantContext


REQUEST_ID = "qualification-request-0001"
VALID_BODY = {
    "action": "chat.complete",
    "input": {"message": "Synthetic summary only.", "response_format": "json"},
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
    def __init__(self, recorder, tenant_ref):
        self.recorder, self.tenant_ref = recorder, tenant_ref

    def resolve(self, claims):
        self.recorder.sequence.append("tenant_context")
        return TenantContext(claims.tenant_claim, self.tenant_ref)


class MetadataRecordingGateway(MockGateway):
    def __init__(self, recorder):
        super().__init__(recorder)
        self.metadata = []

    def complete(self, model_alias, redacted_text, metadata):
        self.metadata.append(dict(metadata))
        return super().complete(model_alias, redacted_text, metadata)


class TrustedRuntimeTests(unittest.TestCase):
    def test_valid_tenant_references_reach_gateway_and_schema_valid_trace_unchanged(self):
        schema = json.loads(
            Path("contracts/phase3/sanitized-trace-envelope.schema.json").read_text()
        )
        validator = Draft202012Validator(schema)
        for tenant_ref in VALID_TENANT_REFS:
            with self.subTest(tenant_ref=tenant_ref):
                runtime, recorder = build_mock_runtime()
                runtime.tenant_resolver = FixedTenantResolver(recorder, tenant_ref)
                gateway = MetadataRecordingGateway(recorder)
                runtime.gateway = gateway

                runtime.execute("Bearer qualification-token", VALID_BODY, REQUEST_ID)

                self.assertEqual(gateway.metadata[0]["tenant_ref"], tenant_ref)
                self.assertEqual(recorder.traces[-1]["tenant_ref"], tenant_ref)
                self.assertEqual(recorder.traces[-1]["outcome"], "success")
                validator.validate(recorder.traces[-1])

    def test_invalid_tenant_references_stop_before_presidio_gateway_and_trace_value(self):
        schema = json.loads(
            Path("contracts/phase3/sanitized-trace-envelope.schema.json").read_text()
        )
        validator = Draft202012Validator(schema)
        for case, tenant_ref in INVALID_TENANT_REFS:
            with self.subTest(case=case):
                runtime, recorder = build_mock_runtime()
                runtime.tenant_resolver = FixedTenantResolver(recorder, tenant_ref)
                gateway = MetadataRecordingGateway(recorder)
                runtime.gateway = gateway

                with self.assertRaises(ControlFailure) as raised:
                    runtime.execute("Bearer qualification-token", VALID_BODY, REQUEST_ID)

                self.assertEqual(
                    (raised.exception.stage, raised.exception.category),
                    ("tenant_context", "malformed_context"),
                )
                self.assertEqual(str(raised.exception), "tenant_context:malformed_context")
                self.assertEqual(recorder.sequence, ["authentication", "tenant_context"])
                self.assertEqual((recorder.litellm_calls, recorder.provider_calls), (0, 0))
                self.assertEqual(gateway.metadata, [])
                self.assertEqual(recorder.traces[-1]["tenant_ref"], None)
                self.assertEqual(recorder.traces[-1]["provider_called"], False)
                validator.validate(recorder.traces[-1])
                if isinstance(tenant_ref, str) and tenant_ref:
                    self.assertFalse(tenant_ref in json.dumps(recorder.traces))
                    self.assertFalse(tenant_ref in str(raised.exception))

    def execute(self, modes=None, body=None, token="Bearer qualification-token"):
        runtime, recorder = build_mock_runtime(modes)
        result = runtime.execute(token, body or VALID_BODY, REQUEST_ID)
        return result, recorder

    def assert_pre_provider_blocked(self, modes=None, body=None, token="Bearer qualification-token"):
        runtime, recorder = build_mock_runtime(modes)
        with self.assertRaises(ControlFailure):
            runtime.execute(token, body or VALID_BODY, REQUEST_ID)
        self.assertEqual(recorder.litellm_calls, 0)
        self.assertEqual(recorder.provider_calls, 0)
        self.assertEqual(recorder.traces[-1]["provider_called"], False)
        return recorder

    def test_success_uses_exact_sequence_and_one_provider_call(self):
        result, recorder = self.execute()
        externally_recorded = [
            stage for stage in STAGES[:-1] if stage != "structured_input_validation"
        ]
        self.assertEqual(recorder.sequence, externally_recorded)
        self.assertEqual(recorder.litellm_calls, 1)
        self.assertEqual(recorder.provider_calls, 1)
        self.assertEqual(result["model"], "secure-financial-chat")
        self.assertEqual(recorder.traces[-1]["outcome"], "success")

    def test_claim_derived_tenant_and_untrusted_body_tenant_rejected(self):
        body = dict(VALID_BODY, tenant_id="attacker-controlled")
        recorder = self.assert_pre_provider_blocked(body=body)
        self.assertEqual(recorder.traces[-1]["failed_stage"], "structured_input_validation")

    def test_nested_tenant_override_is_rejected(self):
        body = {
            "action": "chat.complete",
            "input": {
                "message": "Synthetic summary only.",
                "response_format": "json",
                "context": {"tenantId": "attacker-controlled"},
            },
        }
        self.assert_pre_provider_blocked(body=body)

    def test_each_pre_provider_control_fails_closed(self):
        cases = (
            ({"authentication": "timeout"}, None, "Bearer qualification-token"),
            ({"authentication": "malformed"}, None, "Bearer qualification-token"),
            (None, None, "Bearer invalid"),
            ({"tenant_context": "unavailable"}, None, "Bearer qualification-token"),
            ({"tenant_context": "malformed"}, None, "Bearer qualification-token"),
            ({"authorization": "deny"}, None, "Bearer qualification-token"),
            ({"authorization": "timeout"}, None, "Bearer qualification-token"),
            ({"agent_policy_engine": "deny"}, None, "Bearer qualification-token"),
            ({"agent_policy_engine": "malformed"}, None, "Bearer qualification-token"),
            ({"agent_policy_engine": "timeout"}, None, "Bearer qualification-token"),
            ({"presidio_analyzer": "unavailable"}, None, "Bearer qualification-token"),
            ({"presidio_analyzer": "malformed"}, None, "Bearer qualification-token"),
            ({"presidio_anonymizer": "timeout"}, None, "Bearer qualification-token"),
        )
        for modes, body, token in cases:
            with self.subTest(modes=modes, token=token):
                self.assert_pre_provider_blocked(modes, body, token)

    def test_incomplete_redaction_fails_before_gateway(self):
        protected = "user" + "@" + "example" + ".com"
        body = {
            "action": "chat.complete",
            "input": {"message": "Contact " + protected, "response_format": "json"},
        }
        recorder = self.assert_pre_provider_blocked(
            {"presidio_anonymizer": "incomplete"}, body
        )
        serialized = json.dumps(recorder.traces)
        self.assertNotIn(protected, serialized)

    def test_malformed_provider_output_is_blocked_after_recorded_call(self):
        runtime, recorder = build_mock_runtime({"litellm": "malformed"})
        with self.assertRaises(ControlFailure) as raised:
            runtime.execute("Bearer qualification-token", VALID_BODY, REQUEST_ID)
        self.assertEqual(raised.exception.stage, "structured_output_validation")
        self.assertEqual(recorder.litellm_calls, 1)
        self.assertEqual(recorder.provider_calls, 1)

    def test_trace_is_sanitized(self):
        protected = "user" + "@" + "example" + ".com"
        body = {
            "action": "chat.complete",
            "input": {"message": "Contact " + protected, "response_format": "json"},
        }
        _, recorder = self.execute(body=body)
        serialized = json.dumps(recorder.traces)
        for prohibited in (protected, "qualification-token", "tenant-qualification", body["input"]["message"]):
            self.assertNotIn(prohibited, serialized)
        self.assertEqual(recorder.traces[-1]["detected_categories"], ["EMAIL_ADDRESS"])

    def test_samples_store_no_authoritative_tenant_in_positive_request(self):
        fixture = json.loads(
            Path("tests/phase3/runtime/sample-requests.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("tenant_id", fixture["positive"])
        self.assertIn("tenant_id", fixture["negative_untrusted_tenant"])


if __name__ == "__main__":
    unittest.main()
