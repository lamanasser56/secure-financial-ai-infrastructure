"""Portfolio Phase 4A tool registry reference implementation."""

from .tool_registry import (
    RegistryFailure,
    RiskClass,
    ToolMetadata,
    get_tool_metadata,
    load_registry,
    resolve_tool_preconditions,
)
from .tool_invocation import (
    ALLOWED_STAGE_CATEGORIES,
    FALLBACK_CATEGORY,
    FALLBACK_STAGE,
    ValidatedToolInvocation,
    build_failure_response,
    build_validated_success_response,
    validate_invocation_envelope,
    validate_tool_invocation,
)
from .prompt_injection import (
    PromptInjectionAssessment,
    PromptInjectionAssessor,
    PromptInjectionOutcome,
)
from .tool_policy import (
    PolicyOutcome,
    ToolPolicyDecision,
    ToolPolicyEngine,
    ToolPolicyInput,
)
from .tool_approval import ApprovalContext, ApprovalDecision, ApprovalVerifier
from .tool_governance import (
    GovernedToolInvocation,
    validate_and_govern_tool_invocation,
)
from .tool_audit import build_ai_audit_event, validate_ai_audit_event

__all__ = [
    "RegistryFailure",
    "RiskClass",
    "ToolMetadata",
    "get_tool_metadata",
    "load_registry",
    "resolve_tool_preconditions",
    "ALLOWED_STAGE_CATEGORIES",
    "FALLBACK_CATEGORY",
    "FALLBACK_STAGE",
    "ValidatedToolInvocation",
    "build_failure_response",
    "build_validated_success_response",
    "validate_invocation_envelope",
    "validate_tool_invocation",
    "PromptInjectionAssessment",
    "PromptInjectionAssessor",
    "PromptInjectionOutcome",
    "PolicyOutcome",
    "ToolPolicyDecision",
    "ToolPolicyEngine",
    "ToolPolicyInput",
    "ApprovalContext",
    "ApprovalDecision",
    "ApprovalVerifier",
    "GovernedToolInvocation",
    "validate_and_govern_tool_invocation",
    "build_ai_audit_event",
    "validate_ai_audit_event",
]
