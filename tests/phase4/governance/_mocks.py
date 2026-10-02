"""Non-sensitive Phase 4C repository-qualification mocks."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from runtime.phase3.mocks import MockAuthenticator, MockTenantResolver, Recorder
from runtime.phase3.trusted_runtime import IdentityClaims, TenantContext
from runtime.phase4.prompt_injection import (
    PromptInjectionAssessment, PromptInjectionOutcome,
)
from runtime.phase4.tool_policy import PolicyOutcome, ToolPolicyDecision
from runtime.phase4.tool_registry import ToolMetadata, validate_tool_metadata


class GovernanceRecorder(Recorder):
    def __init__(self):
        super().__init__()
        self.policy_calls = 0
        self.approval_calls = 0
        self.assessment_inputs: list[Any] = []
        self.policy_inputs: list[Any] = []
        self.approval_ids: list[str] = []


class MockToolAuthorizer:
    def __init__(self, recorder: GovernanceRecorder, mode: str = "ok"):
        self.recorder, self.mode = recorder, mode
        self.seen_actions: list[str] = []

    def authorize(
        self, claims: IdentityClaims, tenant: TenantContext, action: str
    ) -> bool:
        self.recorder.sequence.append("authorization")
        self.seen_actions.append(action)
        if self.mode == "timeout":
            raise TimeoutError("authorization")
        if self.mode == "unavailable":
            raise RuntimeError("authorization-sensitive-detail")
        return self.mode != "deny" and "ai:invoke" in claims.scopes


class MockPromptInjectionAssessor:
    def __init__(self, recorder: GovernanceRecorder, mode: str = "clear"):
        self.recorder, self.mode, self.calls = recorder, mode, 0

    def assess(self, arguments: dict[str, Any]) -> Any:
        self.calls += 1
        self.recorder.sequence.append("prompt_injection_assessment")
        self.recorder.assessment_inputs.append(deepcopy(arguments))
        if self.mode == "timeout":
            raise TimeoutError("prompt-injection-sensitive-detail")
        if self.mode == "unavailable":
            raise RuntimeError("prompt-injection-sensitive-detail")
        if self.mode == "malformed":
            return {"outcome": "clear", "indicator_categories": []}
        if self.mode == "unsupported":
            return PromptInjectionAssessment(
                PromptInjectionOutcome.SUSPECTED, ("unapproved_category",)
            )
        if self.mode == "suspected":
            return PromptInjectionAssessment(
                PromptInjectionOutcome.SUSPECTED, ("instruction_override",)
            )
        return PromptInjectionAssessment(PromptInjectionOutcome.CLEAR, ())


class MockToolPolicyEngine:
    def __init__(
        self, recorder: GovernanceRecorder, decision: Any, mode: str = "ok"
    ):
        self.recorder, self.decision, self.mode = recorder, decision, mode
        self.calls = 0

    def evaluate(self, policy_input: Any) -> Any:
        self.calls += 1
        self.recorder.policy_calls += 1
        self.recorder.sequence.append("agent_policy_engine")
        self.recorder.policy_inputs.append(policy_input)
        if self.mode == "timeout":
            raise TimeoutError("policy-sensitive-detail")
        if self.mode == "unavailable":
            raise RuntimeError("policy-sensitive-detail")
        return self.decision


class MockApprovalVerifier:
    def __init__(
        self, recorder: GovernanceRecorder, server_decision: Any,
        mode: str = "ok",
    ):
        self.recorder = recorder
        self.server_decision = server_decision
        self.mode = mode
        self.calls = 0

    def retrieve_verified(self, approval_id: str) -> Any:
        self.calls += 1
        self.recorder.approval_calls += 1
        self.recorder.sequence.append("human_approval_verification")
        self.recorder.approval_ids.append(approval_id)
        if self.mode == "timeout":
            raise TimeoutError("approval-sensitive-detail")
        if self.mode == "unavailable":
            raise RuntimeError("approval-sensitive-detail")
        return deepcopy(self.server_decision)


def build_identity_dependencies(
    recorder: GovernanceRecorder, authorization_mode: str = "ok"
):
    return (
        MockAuthenticator(recorder, "ok"),
        MockTenantResolver(recorder, "ok"),
        MockToolAuthorizer(recorder, authorization_mode),
    )


def load_fixtures() -> dict[str, Any]:
    return json.loads(
        Path("tests/phase4/governance/sample-governance-fixtures.json")
        .read_text(encoding="utf-8")
    )


def registry_requiring_approval() -> dict[str, ToolMetadata]:
    raw = json.loads(
        Path("tests/phase4/registry/sample-registry.json").read_text(
            encoding="utf-8"
        )
    )
    tool = deepcopy(raw["tools"][0])
    tool["risk_classification"] = "irreversible_high_impact"
    tool["operation_type"] = "write"
    tool["approval"] = {
        "required": True,
        "extension_point_ref": "phase-4c-human-approval-extension-point",
    }
    tool["audit_classification"] = "high_sensitivity"
    return {tool["id"]: validate_tool_metadata(tool)}


VALID_REQUEST = {
    "schema_version": 1,
    "request_id": "qualification-request-0001",
    "tool_id": "example_get_cash_position",
    "arguments": {"as_of_date": "2026-08-01"},
}
ALLOW_DECISION = ToolPolicyDecision(PolicyOutcome.ALLOW, "engine_allowed")
DENY_DECISION = ToolPolicyDecision(PolicyOutcome.DENY, "engine_denied")
ENGINE_APPROVAL_DECISION = ToolPolicyDecision(
    PolicyOutcome.REQUIRE_APPROVAL, "engine_require_approval"
)
REGISTRY_APPROVAL_DECISION = ToolPolicyDecision(
    PolicyOutcome.REQUIRE_APPROVAL, "registry_requires_approval"
)
