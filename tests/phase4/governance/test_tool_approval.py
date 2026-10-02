import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from runtime.phase3.trusted_runtime import ControlFailure
from runtime.phase4.tool_approval import (
    ApprovalContext, canonical_arguments_digest, verify_tool_approval,
)
from _mocks import GovernanceRecorder, MockApprovalVerifier, load_fixtures


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


def strict_format_checker():
    checker = FormatChecker()

    @checker.checks("date-time", raises=(TypeError, ValueError))
    def is_date_time(value):
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
            value,
        ):
            return False
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None

    return checker


class CanonicalDigestTests(unittest.TestCase):
    def test_key_order_is_stable(self):
        left = {"z": "non-ascii-\u0627", "a": {"two": 2, "one": 1}}
        right = {"a": {"one": 1, "two": 2}, "z": "non-ascii-\u0627"}
        self.assertEqual(
            canonical_arguments_digest(left), canonical_arguments_digest(right)
        )

    def test_changed_arguments_change_digest(self):
        self.assertNotEqual(
            canonical_arguments_digest({"as_of_date": "2026-08-01"}),
            canonical_arguments_digest({"as_of_date": "2026-08-02"}),
        )

    def test_nan_fails_closed(self):
        with self.assertRaises(ControlFailure) as ctx:
            canonical_arguments_digest({"amount": float("nan")})
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("agent_policy_engine", "argument_digest_failure"),
        )


class ApprovalSchemaTests(unittest.TestCase):
    def setUp(self):
        schema = json.loads(
            Path("contracts/phase4/tool-approval-decision.schema.json")
            .read_text(encoding="utf-8")
        )
        self.validator = Draft202012Validator(
            schema, format_checker=strict_format_checker()
        )
        self.decision = load_fixtures()["approval_decision"]

    def test_valid_fixture(self):
        self.validator.validate(self.decision)

    def test_format_checker_rejects_bad_issued_at(self):
        self.assertFalse(self.validator.is_valid(
            {**self.decision, "issued_at": "not-a-date-time"}
        ))

    def test_format_checker_rejects_bad_expires_at(self):
        self.assertFalse(self.validator.is_valid(
            {**self.decision, "expires_at": "not-a-date-time"}
        ))

    def test_raw_arguments_rejected(self):
        self.assertFalse(self.validator.is_valid(
            {**self.decision, "arguments": {"amount": 100}}
        ))


class ApprovalRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.decision = load_fixtures()["approval_decision"]
        self.context = ApprovalContext(
            request_id="qualification-request-0001",
            tenant_ref="52b6c32a108b587d",
            subject_ref="03163199a392a2e4",
            tool_id="example_get_cash_position",
            tool_version="0.1.0",
            required_action="example_get_cash_position.execute",
            risk_classification="sensitive_financial_read",
            arguments_digest="86eb72efe5c57b2f0fb5d77113f9b7584b34595533a81a9d8bfed7530a138bd1",
        )

    def test_missing_id_does_not_call_verifier(self):
        verifier = self._verifier(self.decision)
        with self.assertRaises(ControlFailure) as ctx:
            verify_tool_approval(verifier, None, self.context, now=NOW)
        self.assertEqual(ctx.exception.category, "missing_decision")
        self.assertEqual(verifier.calls, 0)

    def test_invalid_id_does_not_call_verifier(self):
        verifier = self._verifier(self.decision)
        with self.assertRaises(ControlFailure) as ctx:
            verify_tool_approval(
                verifier, "invalid approval id", self.context, now=NOW
            )
        self.assertEqual(ctx.exception.category, "missing_decision")
        self.assertEqual(verifier.calls, 0)

    def test_valid_id_calls_verifier_exactly_once(self):
        verifier = self._verifier(self.decision)
        result = verify_tool_approval(
            verifier, "approval-qualification-0001", self.context, now=NOW
        )
        self.assertEqual(result.approval_id, "approval-qualification-0001")
        self.assertEqual(verifier.calls, 1)

    def test_denied_rejected(self):
        self._mutation({"decision": "denied"}, "denied_decision")

    def test_expired_rejected(self):
        self._mutation(
            {"expires_at": "2026-08-14T11:59:59Z"}, "expired_decision"
        )

    def test_consumed_rejected(self):
        self._mutation({"consumed": True}, "replayed_decision")

    def test_tenant_mismatch(self):
        self._mutation({"tenant_ref": "0" * 16}, "tenant_mismatch")

    def test_subject_mismatch(self):
        self._mutation({"subject_ref": "0" * 16}, "subject_mismatch")

    def test_request_mismatch(self):
        self._mutation(
            {"request_id": "qualification-request-9999"}, "tool_mismatch"
        )

    def test_tool_id_mismatch(self):
        self._mutation({"tool_id": "different_tool"}, "tool_mismatch")

    def test_tool_version_mismatch(self):
        self._mutation({"tool_version": "9.9.9"}, "tool_mismatch")

    def test_action_mismatch(self):
        self._mutation(
            {"required_action": "different_tool.execute"}, "tool_mismatch"
        )

    def test_risk_mismatch(self):
        self._mutation(
            {"risk_classification": "low_risk_read"}, "tool_mismatch"
        )

    def test_digest_mismatch(self):
        self._mutation(
            {"arguments_digest": "0" * 64}, "arguments_digest_mismatch"
        )

    def test_naive_issued_rejected(self):
        self._mutation(
            {"issued_at": "2026-08-14T11:00:00"}, "malformed_decision"
        )

    def test_naive_expiry_rejected(self):
        self._mutation(
            {"expires_at": "2026-08-14T13:00:00"}, "malformed_decision"
        )

    def test_issued_must_precede_expiry(self):
        self._mutation(
            {
                "issued_at": "2026-08-14T13:00:00Z",
                "expires_at": "2026-08-14T13:00:00Z",
            },
            "malformed_decision",
        )

    def test_future_issued_beyond_skew_rejected(self):
        self._mutation(
            {"issued_at": "2026-08-14T12:06:00Z"}, "malformed_decision"
        )

    def test_timeout_normalized(self):
        self._dependency_failure("timeout", "timeout")

    def test_unavailable_normalized(self):
        self._dependency_failure("unavailable", "unavailable")

    def _mutation(self, mutation, category):
        verifier = self._verifier({**self.decision, **mutation})
        with self.assertRaises(ControlFailure) as ctx:
            verify_tool_approval(
                verifier, "approval-qualification-0001", self.context, now=NOW
            )
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("human_approval_verification", category),
        )
        self.assertEqual(verifier.calls, 1)

    def _dependency_failure(self, mode, category):
        verifier = MockApprovalVerifier(
            GovernanceRecorder(), self.decision, mode=mode
        )
        with self.assertRaises(ControlFailure) as ctx:
            verify_tool_approval(
                verifier, "approval-qualification-0001", self.context, now=NOW
            )
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("human_approval_verification", category),
        )
        self.assertNotIn("sensitive-detail", str(ctx.exception))

    @staticmethod
    def _verifier(decision):
        return MockApprovalVerifier(GovernanceRecorder(), decision)


if __name__ == "__main__":
    unittest.main()
