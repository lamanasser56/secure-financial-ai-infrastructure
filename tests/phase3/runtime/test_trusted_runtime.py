import json
from pathlib import Path
import unittest

from runtime.phase3.mocks import build_mock_runtime
from runtime.phase3.trusted_runtime import ControlFailure, STAGES


REQUEST_ID = "qualification-request-0001"
VALID_BODY = {
    "action": "chat.complete",
    "input": {"message": "Synthetic summary only.", "response_format": "json"},
}


class TrustedRuntimeTests(unittest.TestCase):
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
        self.assertEqual(result["model"], "ai-platformroved-chat")
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
