"""Portfolio Phase 4C fail-closed tool-policy contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from runtime.phase3.trusted_runtime import ControlFailure, PolicyDecision
from runtime.phase4.tool_registry import ToolMetadata


class PolicyOutcome(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


TOOL_POLICY_REASON_CODES = {
    PolicyOutcome.ALLOW: frozenset({"engine_allowed"}),
    PolicyOutcome.DENY: frozenset({"engine_denied"}),
    PolicyOutcome.REQUIRE_APPROVAL: frozenset(
        {"registry_requires_approval", "engine_require_approval"}
    ),
}


@dataclass(frozen=True)
class ToolPolicyInput:
    request_id: str
    tenant_ref: str
    subject_ref: str
    tool_id: str
    tool_version: str
    required_action: str
    risk_classification: str
    arguments_digest: str
    registry_requires_approval: bool


@dataclass(frozen=True)
class ToolPolicyDecision:
    outcome: PolicyOutcome
    reason_code: str


class ToolPolicyEngine(Protocol):
    def evaluate(self, policy_input: ToolPolicyInput) -> ToolPolicyDecision: ...


class ReadOnlyAgentPolicy:
    """Concrete profile for the existing Phase 3/4 interfaces, not a new engine.

    Tool identity/action/risk come from the canonical registry. Writes and
    approval-required operations are denied by this bounded demo profile.
    """

    def __init__(self, tools: dict[str, ToolMetadata]):
        self.tools = dict(tools)

    def evaluate(self, request):
        if isinstance(request, ToolPolicyInput):
            tool = self.tools.get(request.tool_id)
            allowed = (
                tool is not None
                and tool.enabled
                and tool.operation_type.value == "read"
                and not tool.approval.required
                and not request.registry_requires_approval
                and request.tool_version == tool.version
                and request.required_action == tool.authorization.required_action
                and request.risk_classification == tool.risk_classification.value
            )
            return ToolPolicyDecision(
                PolicyOutcome.ALLOW if allowed else PolicyOutcome.DENY,
                "engine_allowed" if allowed else "engine_denied",
            )
        allowed = (
            isinstance(request, dict)
            and set(request) == {"action", "message_length", "response_format", "redaction_required"}
            and request["action"] == "chat.complete"
            and type(request["message_length"]) is int
            and 1 <= request["message_length"] <= 4000
            and request["response_format"] == "json"
            and request["redaction_required"] is True
        )
        return PolicyDecision(allowed, "phase3_chat_allowed" if allowed else "engine_denied")


def validate_policy_decision(
    decision: Any,
    tool: ToolMetadata,
) -> ToolPolicyDecision:
    """Validate the closed outcome/reason mapping and registry approval floor."""
    if not isinstance(decision, ToolPolicyDecision):
        raise ControlFailure("agent_policy_engine", "malformed_decision")
    if not isinstance(decision.outcome, PolicyOutcome):
        raise ControlFailure("agent_policy_engine", "malformed_decision")
    if decision.reason_code not in TOOL_POLICY_REASON_CODES[decision.outcome]:
        raise ControlFailure("agent_policy_engine", "malformed_decision")

    if tool.approval.required:
        if decision.outcome is PolicyOutcome.ALLOW:
            raise ControlFailure("agent_policy_engine", "malformed_decision")
        if (
            decision.outcome is PolicyOutcome.REQUIRE_APPROVAL
            and decision.reason_code != "registry_requires_approval"
        ):
            raise ControlFailure("agent_policy_engine", "malformed_decision")
    elif decision.reason_code == "registry_requires_approval":
        raise ControlFailure("agent_policy_engine", "malformed_decision")
    return decision


def evaluate_tool_policy(
    policy_engine: ToolPolicyEngine,
    policy_input: ToolPolicyInput,
    tool: ToolMetadata,
) -> ToolPolicyDecision:
    try:
        decision = policy_engine.evaluate(policy_input)
    except ControlFailure as exc:
        if exc.stage == "agent_policy_engine" and exc.category in {
            "timeout", "unavailable"
        }:
            raise
        raise ControlFailure("agent_policy_engine", "unavailable") from exc
    except TimeoutError as exc:
        raise ControlFailure("agent_policy_engine", "timeout") from exc
    except Exception as exc:
        raise ControlFailure("agent_policy_engine", "unavailable") from exc
    return validate_policy_decision(decision, tool)
