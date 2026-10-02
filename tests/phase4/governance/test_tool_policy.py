import unittest

from runtime.phase3.trusted_runtime import ControlFailure
from runtime.phase4.tool_policy import (
    PolicyOutcome, ToolPolicyDecision, validate_policy_decision,
)
from runtime.phase4.tool_registry import load_registry
from _mocks import registry_requiring_approval


class ToolPolicyTests(unittest.TestCase):
    def setUp(self):
        self.read_tool = load_registry(
            "tests/phase4/registry/sample-registry.json"
        )["example_get_cash_position"]
        self.approval_tool = registry_requiring_approval()[
            "example_get_cash_position"
        ]

    def test_allow_engine_allowed_valid(self):
        result = validate_policy_decision(
            ToolPolicyDecision(PolicyOutcome.ALLOW, "engine_allowed"),
            self.read_tool,
        )
        self.assertEqual(result.outcome, PolicyOutcome.ALLOW)

    def test_deny_engine_denied_valid(self):
        result = validate_policy_decision(
            ToolPolicyDecision(PolicyOutcome.DENY, "engine_denied"),
            self.read_tool,
        )
        self.assertEqual(result.outcome, PolicyOutcome.DENY)

    def test_engine_require_approval_valid_for_non_registry_tool(self):
        result = validate_policy_decision(
            ToolPolicyDecision(
                PolicyOutcome.REQUIRE_APPROVAL, "engine_require_approval"
            ), self.read_tool,
        )
        self.assertEqual(result.outcome, PolicyOutcome.REQUIRE_APPROVAL)

    def test_registry_reason_valid_for_registry_tool(self):
        result = validate_policy_decision(
            ToolPolicyDecision(
                PolicyOutcome.REQUIRE_APPROVAL, "registry_requires_approval"
            ), self.approval_tool,
        )
        self.assertEqual(result.reason_code, "registry_requires_approval")

    def test_allow_engine_denied_rejected(self):
        self._malformed(PolicyOutcome.ALLOW, "engine_denied", self.read_tool)

    def test_deny_engine_allowed_rejected(self):
        self._malformed(PolicyOutcome.DENY, "engine_allowed", self.read_tool)

    def test_require_approval_engine_allowed_rejected(self):
        self._malformed(
            PolicyOutcome.REQUIRE_APPROVAL, "engine_allowed", self.read_tool
        )

    def test_registry_tool_policy_allow_rejected(self):
        self._malformed(
            PolicyOutcome.ALLOW, "engine_allowed", self.approval_tool
        )

    def test_registry_tool_engine_reason_rejected(self):
        self._malformed(
            PolicyOutcome.REQUIRE_APPROVAL,
            "engine_require_approval",
            self.approval_tool,
        )

    def test_registry_reason_rejected_for_non_registry_tool(self):
        self._malformed(
            PolicyOutcome.REQUIRE_APPROVAL,
            "registry_requires_approval",
            self.read_tool,
        )

    def test_plain_dict_rejected(self):
        with self.assertRaises(ControlFailure) as ctx:
            validate_policy_decision(
                {"outcome": "allow", "reason_code": "engine_allowed"},
                self.read_tool,
            )
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("agent_policy_engine", "malformed_decision"),
        )

    def _malformed(self, outcome, reason, tool):
        with self.assertRaises(ControlFailure) as ctx:
            validate_policy_decision(ToolPolicyDecision(outcome, reason), tool)
        self.assertEqual(
            (ctx.exception.stage, ctx.exception.category),
            ("agent_policy_engine", "malformed_decision"),
        )


if __name__ == "__main__":
    unittest.main()
