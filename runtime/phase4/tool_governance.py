"""Portfolio Phase 4C complete tool-governance composition boundary."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from runtime.phase3.trusted_runtime import (
    Authenticator, Authorizer, ControlFailure, TenantContext, TenantResolver,
)
from runtime.phase4.prompt_injection import (
    PromptInjectionAssessor, assess_prompt_injection,
)
from runtime.phase4.tool_approval import (
    ApprovalContext, ApprovalVerifier, canonical_arguments_digest,
    verify_tool_approval,
)
from runtime.phase4.tool_invocation import _validate_tool_invocation_pending_governance
from runtime.phase4.tool_policy import (
    PolicyOutcome, ToolPolicyEngine, ToolPolicyInput, evaluate_tool_policy,
)
from runtime.phase4.tool_registry import ToolMetadata


@dataclass(frozen=True)
class GovernedToolInvocation:
    """Governance-qualified invocation, not an execution grant or result."""

    request_id: str
    tool: ToolMetadata
    tenant: TenantContext
    subject_ref: str
    arguments: dict[str, Any]
    arguments_digest: str
    policy_outcome: PolicyOutcome
    policy_reason_code: str
    approval_id: str | None


def validate_and_govern_tool_invocation(
    authenticator: Authenticator,
    tenant_resolver: TenantResolver,
    authorizer: Authorizer,
    injection_assessor: PromptInjectionAssessor,
    policy_engine: ToolPolicyEngine,
    approval_verifier: ApprovalVerifier,
    registry: dict[str, ToolMetadata],
    authorization_header: str,
    body: Any,
    approval_id: str | None,
    *,
    now: datetime,
) -> GovernedToolInvocation:
    """Apply every Phase 4C control and execute no tool."""
    stage = "structured_input_validation"
    try:
        pending = _validate_tool_invocation_pending_governance(
            authenticator, tenant_resolver, authorizer, registry,
            authorization_header, body,
        )
        tool = pending.registry_ready_tool.metadata
        subject_ref = hashlib.sha256(
            pending.claims.subject.encode("utf-8")
        ).hexdigest()[:16]

        stage = "prompt_injection_assessment"
        assess_prompt_injection(injection_assessor, pending.arguments)

        stage = "agent_policy_engine"
        arguments_digest = canonical_arguments_digest(pending.arguments)
        policy_input = ToolPolicyInput(
            request_id=pending.request_id,
            tenant_ref=pending.tenant.tenant_ref,
            subject_ref=subject_ref,
            tool_id=tool.id,
            tool_version=tool.version,
            required_action=tool.authorization.required_action,
            risk_classification=tool.risk_classification.value,
            arguments_digest=arguments_digest,
            registry_requires_approval=tool.approval.required,
        )
        decision = evaluate_tool_policy(policy_engine, policy_input, tool)
        if decision.outcome is PolicyOutcome.DENY:
            raise ControlFailure("agent_policy_engine", "denied")

        verified_approval_id = None
        if decision.outcome is PolicyOutcome.REQUIRE_APPROVAL:
            stage = "human_approval_verification"
            verified = verify_tool_approval(
                approval_verifier,
                approval_id,
                ApprovalContext(
                    request_id=pending.request_id,
                    tenant_ref=pending.tenant.tenant_ref,
                    subject_ref=subject_ref,
                    tool_id=tool.id,
                    tool_version=tool.version,
                    required_action=tool.authorization.required_action,
                    risk_classification=tool.risk_classification.value,
                    arguments_digest=arguments_digest,
                ),
                now=now,
            )
            verified_approval_id = verified.approval_id

        return GovernedToolInvocation(
            request_id=pending.request_id,
            tool=tool,
            tenant=pending.tenant,
            subject_ref=subject_ref,
            arguments=dict(pending.arguments),
            arguments_digest=arguments_digest,
            policy_outcome=decision.outcome,
            policy_reason_code=decision.reason_code,
            approval_id=verified_approval_id,
        )
    except ControlFailure:
        raise
    except TimeoutError as exc:
        raise ControlFailure(stage, "timeout") from exc
    except Exception as exc:
        raise ControlFailure(stage, "unavailable") from exc
