from __future__ import annotations

import hashlib
import inspect
import unittest
from datetime import datetime, timezone
from typing import Any

from runtime.phase3.mocks import (
    MockAuthenticator,
    MockTenantResolver,
    Recorder,
    build_mock_runtime,
)
from runtime.phase3.trusted_runtime import (
    APPROVED_MODEL_ALIAS,
    ControlFailure,
    IdentityClaims,
    STAGES,
    TenantContext,
)
from runtime.phase4.prompt_injection import (
    PromptInjectionAssessment,
    PromptInjectionOutcome,
)
from runtime.phase4.tool_approval import canonical_arguments_digest
from runtime.phase4.tool_governance import (
    GovernedToolInvocation,
    validate_and_govern_tool_invocation,
)
from runtime.phase4.tool_policy import (
    PolicyOutcome,
    ToolPolicyDecision,
)
from runtime.phase4.tool_registry import ToolMetadata, validate_tool_metadata


REQUEST_ID = "qualification-request-0001"
VALID_CHAT_BODY = {
    "action": "chat.complete",
    "input": {"message": "Synthetic summary only.", "response_format": "json"},
}
VALID_TOOL_BODY = {
    "schema_version": 1,
    "request_id": REQUEST_ID,
    "tool_id": "example_get_cash_position",
    "arguments": {"as_of_date": "2026-08-15"},
}
NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


class Phase3BoundaryTests(unittest.TestCase):
    def assert_blocked_before_provider(
        self,
        *,
        modes: dict[str, str] | None = None,
        body: Any = VALID_CHAT_BODY,
        token: str = "Bearer qualification-token",
    ) -> Recorder:
        runtime, recorder = build_mock_runtime(modes)
        with self.assertRaises(ControlFailure):
            runtime.execute(token, body, REQUEST_ID)
        self.assertEqual(recorder.litellm_calls, 0)
        self.assertEqual(recorder.provider_calls, 0)
        self.assertNotIn("litellm", recorder.sequence)
        self.assertNotIn("provider", recorder.sequence)
        return recorder

    def test_every_required_pre_provider_failure_stops_downstream_calls(self):
        cases = (
            ({"authentication": "unavailable"}, VALID_CHAT_BODY, "Bearer qualification-token"),
            ({"tenant_context": "unavailable"}, VALID_CHAT_BODY, "Bearer qualification-token"),
            ({"authorization": "deny"}, VALID_CHAT_BODY, "Bearer qualification-token"),
            (None, {**VALID_CHAT_BODY, "model": "attacker-model"}, "Bearer qualification-token"),
            ({"agent_policy_engine": "deny"}, VALID_CHAT_BODY, "Bearer qualification-token"),
            ({"presidio_analyzer": "unavailable"}, VALID_CHAT_BODY, "Bearer qualification-token"),
        )
        for modes, body, token in cases:
            with self.subTest(modes=modes, body=body):
                self.assert_blocked_before_provider(modes=modes, body=body, token=token)

        protected_body = {
            "action": "chat.complete",
            "input": {
                "message": "Contact qualification@example.com",
                "response_format": "json",
            },
        }
        self.assert_blocked_before_provider(
            modes={"presidio_anonymizer": "incomplete"},
            body=protected_body,
        )

    def test_success_order_and_model_alias_are_exact(self):
        runtime, recorder = build_mock_runtime()
        result = runtime.execute(
            "Bearer qualification-token", VALID_CHAT_BODY, REQUEST_ID
        )
        recorded_stages = [
            stage
            for stage in STAGES[:-1]
            if stage != "structured_input_validation"
        ]
        self.assertEqual(recorder.sequence, recorded_stages)
        self.assertEqual(result["model"], APPROVED_MODEL_ALIAS)
        self.assertEqual(recorder.litellm_calls, 1)
        self.assertEqual(recorder.provider_calls, 1)

    def test_request_cannot_select_tenant_model_provider_policy_or_redaction(self):
        overrides = {
            "tenant_id": "attacker-tenant",
            "model": "attacker-model",
            "provider_url": "https://attacker.invalid",
            "policy_result": "allow",
            "redaction_bypass": True,
        }
        for key, value in overrides.items():
            with self.subTest(key=key):
                self.assert_blocked_before_provider(
                    body={**VALID_CHAT_BODY, key: value}
                )


class GovernanceRecorder(Recorder):
    def __init__(self) -> None:
        super().__init__()
        self.registry_recorded = False
        self.execution_calls = 0


class RecordingRegistry(dict[str, ToolMetadata]):
    def __init__(
        self, tool: ToolMetadata, recorder: GovernanceRecorder
    ) -> None:
        super().__init__({tool.id: tool})
        self.recorder = recorder

    def __contains__(self, key: object) -> bool:
        if not self.recorder.registry_recorded:
            self.recorder.sequence.append("registry_validation")
            self.recorder.registry_recorded = True
        return super().__contains__(key)


class ToolAuthorizer:
    def __init__(self, recorder: GovernanceRecorder) -> None:
        self.recorder = recorder

    def authorize(
        self, claims: IdentityClaims, tenant: TenantContext, action: str
    ) -> bool:
        self.recorder.sequence.append("authorization")
        return (
            claims.subject == "qualification-subject"
            and tenant.tenant_id == "tenant-qualification"
            and action == "finance.read"
        )


class InjectionAssessor:
    def __init__(self, recorder: GovernanceRecorder) -> None:
        self.recorder = recorder

    def assess(self, arguments: dict[str, Any]) -> PromptInjectionAssessment:
        self.recorder.sequence.append("prompt_injection_assessment")
        return PromptInjectionAssessment(PromptInjectionOutcome.CLEAR, ())


class ApprovalPolicy:
    def __init__(self, recorder: GovernanceRecorder) -> None:
        self.recorder = recorder

    def evaluate(self, policy_input: Any) -> ToolPolicyDecision:
        self.recorder.sequence.append("agent_policy_engine")
        return ToolPolicyDecision(
            PolicyOutcome.REQUIRE_APPROVAL, "registry_requires_approval"
        )


class ApprovalVerifier:
    def __init__(
        self, recorder: GovernanceRecorder, decision: dict[str, Any]
    ) -> None:
        self.recorder = recorder
        self.decision = decision

    def retrieve_verified(self, approval_id: str) -> dict[str, Any]:
        self.recorder.sequence.append("human_approval_verification")
        return dict(self.decision)


def approval_tool() -> ToolMetadata:
    return validate_tool_metadata(
        {
            "id": "example_get_cash_position",
            "name": "Qualified cash position",
            "description": (
                "Returns one validated synthetic cash position for control-boundary qualification."
            ),
            "version": "1.0.0",
            "owner": "portfolio-infrastructure",
            "enabled": True,
            "risk_classification": "irreversible_high_impact",
            "operation_type": "write",
            "input_schema_ref": "contracts/phase4/tools/example.input.json",
            "output_schema_ref": "contracts/phase4/tools/example.output.json",
            "authorization": {"required_action": "finance.read"},
            "approval": {
                "required": True,
                "extension_point_ref": "phase-4c-approval",
            },
            "audit_classification": "high_sensitivity",
            "source_system": "internal",
            "execution_boundary": {
                "timeout_seconds": 10,
                "max_calls_per_turn": 1,
            },
        }
    )


def approval_decision() -> dict[str, Any]:
    arguments_digest = canonical_arguments_digest(VALID_TOOL_BODY["arguments"])
    tenant_ref = hashlib.sha256(b"tenant-qualification").hexdigest()[:16]
    subject_ref = hashlib.sha256(b"qualification-subject").hexdigest()[:16]
    return {
        "schema_version": 1,
        "approval_id": "approval-qualification-0001",
        "decision": "approved",
        "request_id": REQUEST_ID,
        "tenant_ref": tenant_ref,
        "subject_ref": subject_ref,
        "tool_id": "example_get_cash_position",
        "tool_version": "1.0.0",
        "required_action": "finance.read",
        "risk_classification": "irreversible_high_impact",
        "arguments_digest": arguments_digest,
        "issued_at": "2026-08-15T11:00:00Z",
        "expires_at": "2026-08-15T13:00:00Z",
        "consumed": False,
    }


class Phase4BoundaryTests(unittest.TestCase):
    def test_governance_order_includes_registry_policy_and_approval_without_execution(self):
        recorder = GovernanceRecorder()
        registry = RecordingRegistry(approval_tool(), recorder)
        result = validate_and_govern_tool_invocation(
            MockAuthenticator(recorder),
            MockTenantResolver(recorder),
            ToolAuthorizer(recorder),
            InjectionAssessor(recorder),
            ApprovalPolicy(recorder),
            ApprovalVerifier(recorder, approval_decision()),
            registry,
            "Bearer qualification-token",
            VALID_TOOL_BODY,
            "approval-qualification-0001",
            now=NOW,
        )

        self.assertIsInstance(result, GovernedToolInvocation)
        self.assertEqual(
            recorder.sequence,
            [
                "authentication",
                "tenant_context",
                "registry_validation",
                "authorization",
                "prompt_injection_assessment",
                "agent_policy_engine",
                "human_approval_verification",
            ],
        )
        self.assertEqual(recorder.execution_calls, 0)

    def test_governance_boundary_has_no_executor_or_provider_fallback(self):
        parameters = inspect.signature(
            validate_and_govern_tool_invocation
        ).parameters
        for forbidden in (
            "executor",
            "gateway",
            "litellm",
            "provider",
            "provider_url",
            "model",
            "skip_redaction",
            "policy_result",
        ):
            self.assertNotIn(forbidden, parameters)


if __name__ == "__main__":
    unittest.main()
