import inspect
import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from runtime.phase3.trusted_runtime import ControlFailure
from runtime.phase4.tool_audit import (
    build_ai_audit_event, validate_ai_audit_event,
)
from runtime.phase4.tool_policy import PolicyOutcome
from _mocks import load_fixtures


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


class AuditSchemaTests(unittest.TestCase):
    def setUp(self):
        schema = json.loads(
            Path("contracts/phase4/ai-audit-event.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.validator = Draft202012Validator(
            schema, format_checker=strict_format_checker()
        )
        self.event = load_fixtures()["audit_event"]

    def test_valid_fixture(self):
        self.validator.validate(self.event)

    def test_format_checker_rejects_invalid_occurred_at(self):
        self.assertFalse(self.validator.is_valid(
            {**self.event, "occurred_at": "not-a-date-time"}
        ))

    def test_allow_engine_denied_rejected(self):
        self._pair("allow", "engine_denied")

    def test_deny_engine_allowed_rejected(self):
        self._pair("deny", "engine_allowed")

    def test_require_approval_engine_allowed_rejected(self):
        self._pair("require_approval", "engine_allowed")

    def test_sensitive_and_raw_fields_rejected(self):
        for key, value in {
            "prompt": "forbidden", "arguments": {"amount": 100},
            "result": {"amount": 100}, "financial_value": 100,
            "secret": "forbidden", "token": "forbidden",
            "stack_trace": "forbidden", "provider_error": "forbidden",
        }.items():
            with self.subTest(key=key):
                self.assertFalse(self.validator.is_valid(
                    {**self.event, key: value}
                ))

    def test_failure_stage_category_pair_is_closed(self):
        event = {
            **self.event,
            "governance_result": "blocked",
            "failure_stage": "agent_policy_engine",
            "failure_category": "missing_decision",
        }
        self.assertFalse(self.validator.is_valid(event))

    def _pair(self, outcome, reason):
        self.assertFalse(self.validator.is_valid({
            **self.event, "policy_outcome": outcome,
            "policy_reason_code": reason,
        }))


class AuditRuntimeTests(unittest.TestCase):
    def test_builder_emits_and_validates_allowlisted_event(self):
        event = build_ai_audit_event(
            event_id="audit-qualification-0001",
            occurred_at=datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc),
            request_id="qualification-request-0001",
            tenant_ref="52b6c32a108b587d",
            subject_ref="03163199a392a2e4",
            tool_id="example_get_cash_position",
            tool_version="0.1.0",
            required_action="example_get_cash_position.execute",
            risk_classification="sensitive_financial_read",
            authorization_result="allowed", injection_result="clear",
            indicator_categories=(), policy_outcome=PolicyOutcome.ALLOW,
            policy_reason_code="engine_allowed",
            approval_result="not_required", governance_result="qualified",
            failure=None,
        )
        self.assertEqual(validate_ai_audit_event(event), event)
        serialized = json.dumps(event)
        for forbidden in (
            '"prompt"', '"arguments"', '"result"', '"financial_value"',
            '"stack_trace"', '"provider_error"',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_builder_has_no_raw_exception_parameter(self):
        params = inspect.signature(build_ai_audit_event).parameters
        self.assertNotIn("exception", params)
        self.assertNotIn("error_message", params)

    def test_malformed_event_fails_closed(self):
        with self.assertRaises(ControlFailure) as ctx:
            validate_ai_audit_event({"schema_version": 1, "prompt": "forbidden"})
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("audit", "invalid_event"),
        )


if __name__ == "__main__":
    unittest.main()
