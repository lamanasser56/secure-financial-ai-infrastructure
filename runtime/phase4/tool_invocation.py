"""Portfolio Phase 4B Tool Invocation Request/Response Validation.

Validates a tool invocation request envelope, resolves the requested tool
through the canonical Phase 4A registry, validates the request's arguments
against that tool's registered input schema, and constructs a validated
success response only after the raw result has passed the tool's registered
output validator. Authentication, Tenant Context resolution, and
Authorization reuse the exact Phase 3 Authenticator/TenantResolver/Authorizer
Protocols and the ControlFailure exception type (runtime/phase3/
trusted_runtime.py) -- neither redefined nor duplicated. The private helper
_contains_tenant_key is NOT imported (it is not an approved Protocol/export);
a local, narrowly-scoped equivalent enforces the same documented tenant-key
policy against real tool arguments below.

This module executes no tool, calls no external system, and takes no
financial action. validate_tool_invocation() stops at Structured Input
Validation. The Agent Policy Engine extension, Presidio/redaction, LiteLLM,
external-provider execution, and a real coordinator invoking any of this
end-to-end are Phase 4C/Phase 5 work and do not exist in this repository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from runtime.phase3.trusted_runtime import (
    Authenticator,
    Authorizer,
    ControlFailure,
    CORRELATION_PATTERN,
    IdentityClaims,
    TenantContext,
    TenantResolver,
    is_valid_tenant_ref,
)
from runtime.phase4.tool_registry import (
    ID_PATTERN as TOOL_ID_PATTERN,
    RegistryReadyToolPendingGovernance,
    RegistryFailure,
    ToolMetadata,
    _resolve_registry_readiness_for_governance,
    get_tool_metadata,
    resolve_tool_preconditions,
)

REQUEST_ID_PATTERN = CORRELATION_PATTERN
_DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
TOOL_ID_MIN_LENGTH = 3
TOOL_ID_MAX_LENGTH = 64

# Mirrors runtime/phase3/trusted_runtime.py's TENANT_KEYS exactly. Duplicated
# deliberately: _contains_tenant_key is a private Phase 3 implementation
# helper, not an approved Protocol/export. This is real argument-data
# enforcement (Phase 4B has real arguments to inspect), not the rejected
# Phase 4A metadata-identifier substring scan.
TENANT_SHAPED_KEYS = frozenset({"tenant", "tenant_id", "tenantid", "tenant-id"})

ALLOWED_STAGE_CATEGORIES: dict[str, frozenset[str]] = {
    "authentication": frozenset({"invalid_token", "malformed_claims", "timeout", "unavailable"}),
    "tenant_context": frozenset({"malformed_context", "timeout", "unavailable"}),
    "authorization": frozenset({"denied", "timeout", "unavailable"}),
    "structured_input_validation": frozenset({
        "invalid_request", "unknown_tool", "disabled_tool", "schema_deferred",
        "approval_required_no_decision", "malformed_metadata",
        "unsupported_risk_class", "missing_authorization", "registry_unreadable",
        "argument_schema_mismatch",
    }),
    "prompt_injection_assessment": frozenset({
        "timeout", "unavailable", "malformed_assessment",
        "unsupported_indicator_category", "suspected_injection",
    }),
    "agent_policy_engine": frozenset({
        "timeout", "unavailable", "denied", "malformed_decision",
        "argument_digest_failure",
    }),
    "human_approval_verification": frozenset({
        "timeout", "unavailable", "missing_decision", "denied_decision",
        "expired_decision", "replayed_decision", "tenant_mismatch",
        "subject_mismatch", "tool_mismatch", "arguments_digest_mismatch",
        "malformed_decision",
    }),
    "audit": frozenset({"invalid_event"}),
    "structured_output_validation": frozenset({"output_schema_mismatch"}),
}
FALLBACK_STAGE = "structured_input_validation"
FALLBACK_CATEGORY = "invalid_request"


def _call(stage: str, operation):
    try:
        return operation()
    except ControlFailure:
        raise
    except TimeoutError as exc:
        raise ControlFailure(stage, "timeout") from exc
    except Exception as exc:
        raise ControlFailure(stage, "unavailable") from exc


def _contains_tenant_shaped_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("_", "-")
            if normalized in TENANT_SHAPED_KEYS or normalized.replace("-", "") == "tenantid":
                return True
            if _contains_tenant_shaped_key(child):
                return True
    if isinstance(value, list):
        return any(_contains_tenant_shaped_key(item) for item in value)
    return False


def _is_valid_request_id(value: Any) -> bool:
    return isinstance(value, str) and REQUEST_ID_PATTERN.fullmatch(value) is not None


def _is_valid_tool_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and TOOL_ID_MIN_LENGTH <= len(value) <= TOOL_ID_MAX_LENGTH
        and TOOL_ID_PATTERN.fullmatch(value) is not None
    )


def _validate_example_get_cash_position_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    if set(arguments) - {"as_of_date"}:
        raise ControlFailure("structured_input_validation", "argument_schema_mismatch")
    if "as_of_date" in arguments:
        value = arguments["as_of_date"]
        if not isinstance(value, str) or not _DATE_PATTERN.fullmatch(value):
            raise ControlFailure("structured_input_validation", "argument_schema_mismatch")
    return dict(arguments)


def validate_example_get_cash_position_output(value: Any) -> dict[str, Any]:
    """Validates a GIVEN output value against the registered output schema.
    No caller in this repository invokes this with real tool output -- that
    requires real execution, which is Phase 5."""
    if not isinstance(value, dict) or set(value) != {"as_of_date", "cash_position_minor_units", "currency"}:
        raise ControlFailure("structured_output_validation", "output_schema_mismatch")
    if not isinstance(value["as_of_date"], str) or not _DATE_PATTERN.fullmatch(value["as_of_date"]):
        raise ControlFailure("structured_output_validation", "output_schema_mismatch")
    amount = value["cash_position_minor_units"]
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise ControlFailure("structured_output_validation", "output_schema_mismatch")
    if value["currency"] != "SAR":
        raise ControlFailure("structured_output_validation", "output_schema_mismatch")
    return dict(value)


# Only tools with real (non-deferred) schemas get an entry. A tool with no
# entry here fails closed rather than silently accepting/emitting
# unvalidated data.
ARGUMENT_VALIDATORS = {"example_get_cash_position": _validate_example_get_cash_position_arguments}
OUTPUT_VALIDATORS = {"example_get_cash_position": validate_example_get_cash_position_output}


def _validate_tool_arguments(tool: ToolMetadata, arguments: dict[str, Any]) -> dict[str, Any]:
    validator = ARGUMENT_VALIDATORS.get(tool.id)
    if validator is None:
        raise ControlFailure("structured_input_validation", "argument_schema_mismatch")
    return validator(arguments)


def _lookup_tool_for_routing(registry: dict[str, ToolMetadata], tool_id: Any) -> ToolMetadata:
    """Minimal, unconditional lookup used only to obtain the registry-
    declared authorization action. Deliberately does NOT apply the
    enabled/schema/approval gates (resolve_tool_preconditions) -- those must
    not be evaluated, and must not be able to leak a tool's enabled or
    approval state, before Authorization succeeds. See
    docs/phase4/phase-4b-tool-invocation-contract.md's control-order section."""
    if not _is_valid_tool_id(tool_id):
        raise ControlFailure("structured_input_validation", "invalid_request")
    try:
        return get_tool_metadata(registry, tool_id)
    except RegistryFailure as exc:
        raise ControlFailure("structured_input_validation", exc.category) from exc


def validate_invocation_envelope(body: Any) -> tuple[str, str, dict[str, Any]]:
    """Full envelope validation against contracts/phase4/tool-invocation-
    request.schema.json. Returns (request_id, tool_id, arguments)."""
    if not isinstance(body, dict) or _contains_tenant_shaped_key(body):
        raise ControlFailure("structured_input_validation", "invalid_request")
    if set(body) != {"schema_version", "request_id", "tool_id", "arguments"}:
        raise ControlFailure("structured_input_validation", "invalid_request")
    schema_version = body.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        raise ControlFailure("structured_input_validation", "invalid_request")
    request_id = body.get("request_id")
    if not _is_valid_request_id(request_id):
        raise ControlFailure("structured_input_validation", "invalid_request")
    tool_id = body.get("tool_id")
    if not _is_valid_tool_id(tool_id):
        raise ControlFailure("structured_input_validation", "invalid_request")
    arguments = body.get("arguments")
    if not isinstance(arguments, dict):
        raise ControlFailure("structured_input_validation", "invalid_request")
    return request_id, tool_id, arguments


@dataclass(frozen=True)
class ValidatedToolInvocation:
    request_id: str
    tool: ToolMetadata
    tenant: TenantContext
    arguments: dict[str, Any]


@dataclass(frozen=True)
class PendingGovernanceToolInvocation:
    """Validated invocation whose Phase 4C governance remains pending.

    This package-internal state is not execution-ready and is not exported
    through runtime.phase4.
    """

    request_id: str
    registry_ready_tool: RegistryReadyToolPendingGovernance
    claims: IdentityClaims
    tenant: TenantContext
    arguments: dict[str, Any]


def _authenticate_resolve_and_authorize(
    authenticator: Authenticator,
    tenant_resolver: TenantResolver,
    authorizer: Authorizer,
    registry: dict[str, ToolMetadata],
    authorization_header: str,
    body: Any,
) -> tuple[IdentityClaims, TenantContext, ToolMetadata]:
    stage = "authentication"
    claims = _call(stage, lambda: authenticator.authenticate(authorization_header))
    if not isinstance(claims, IdentityClaims) or not claims.subject or not claims.tenant_claim:
        raise ControlFailure(stage, "malformed_claims")

    stage = "tenant_context"
    tenant = _call(stage, lambda: tenant_resolver.resolve(claims))
    if (
        not isinstance(tenant, TenantContext)
        or not tenant.tenant_id
        or not is_valid_tenant_ref(tenant.tenant_ref)
    ):
        raise ControlFailure(stage, "malformed_context")

    tool = _lookup_tool_for_routing(
        registry, body.get("tool_id") if isinstance(body, dict) else None
    )
    stage = "authorization"
    allowed = _call(
        stage,
        lambda: authorizer.authorize(
            claims, tenant, tool.authorization.required_action
        ),
    )
    if allowed is not True:
        raise ControlFailure(stage, "denied")
    return claims, tenant, tool


def validate_tool_invocation(
    authenticator: Authenticator,
    tenant_resolver: TenantResolver,
    authorizer: Authorizer,
    registry: dict[str, ToolMetadata],
    authorization_header: str,
    body: Any,
) -> ValidatedToolInvocation:
    """See docs/phase4/phase-4b-tool-invocation-contract.md's control-order
    section for the exact sequence and why the registry precondition gate
    runs after Authorization, not before.

    Sequence: Authentication -> Tenant Context -> minimal routing lookup
    (get_tool_metadata, unconditional) -> Authorization (using the
    registry-derived required_action) -> registry precondition gate
    (resolve_tool_preconditions, run only after Authorization succeeds) ->
    Structured Input Validation (full envelope + argument schema). Stops
    there -- no Agent Policy Engine, Presidio, LiteLLM, external-provider
    call, or execution happens anywhere in this repository.
    """
    _claims, tenant, tool = _authenticate_resolve_and_authorize(
        authenticator, tenant_resolver, authorizer, registry,
        authorization_header, body,
    )

    stage = "structured_input_validation"
    try:
        tool = resolve_tool_preconditions(registry, tool.id)
    except RegistryFailure as exc:
        raise ControlFailure(stage, exc.category) from exc

    request_id, _tool_id, arguments = validate_invocation_envelope(body)
    validated_arguments = _validate_tool_arguments(tool, arguments)

    return ValidatedToolInvocation(request_id=request_id, tool=tool, tenant=tenant, arguments=validated_arguments)


def _validate_tool_invocation_pending_governance(
    authenticator: Authenticator,
    tenant_resolver: TenantResolver,
    authorizer: Authorizer,
    registry: dict[str, ToolMetadata],
    authorization_header: str,
    body: Any,
) -> PendingGovernanceToolInvocation:
    claims, tenant, routed_tool = _authenticate_resolve_and_authorize(
        authenticator, tenant_resolver, authorizer, registry,
        authorization_header, body,
    )
    stage = "structured_input_validation"
    try:
        registry_ready_tool = _resolve_registry_readiness_for_governance(
            registry, routed_tool.id
        )
    except RegistryFailure as exc:
        raise ControlFailure(stage, exc.category) from exc
    request_id, _tool_id, arguments = validate_invocation_envelope(body)
    validated_arguments = _validate_tool_arguments(
        registry_ready_tool.metadata, arguments
    )
    return PendingGovernanceToolInvocation(
        request_id=request_id,
        registry_ready_tool=registry_ready_tool,
        claims=claims,
        tenant=tenant,
        arguments=validated_arguments,
    )


def build_validated_success_response(request_id: str, tool: ToolMetadata, raw_result: Any) -> dict[str, Any]:
    """The only way to construct a status: "success" envelope. Fails closed
    if no output validator is registered for this tool, and fails closed if
    raw_result does not pass that validator -- a bypass around Structured
    Output Validation is not possible through this function."""
    if (
        not _is_valid_request_id(request_id)
        or not isinstance(tool, ToolMetadata)
        or not _is_valid_tool_id(tool.id)
    ):
        raise ControlFailure("structured_output_validation", "output_schema_mismatch")
    validator = OUTPUT_VALIDATORS.get(tool.id)
    if validator is None:
        raise ControlFailure("structured_output_validation", "output_schema_mismatch")
    validated_result = validator(raw_result)
    return {
        "schema_version": 1, "request_id": request_id, "tool_id": tool.id,
        "status": "success", "result": validated_result,
    }


def build_failure_response(
    request_id: str | None, tool_id: str | None, failure: ControlFailure
) -> dict[str, Any]:
    """Normalizes any (stage, category) not in the closed
    ALLOWED_STAGE_CATEGORIES map to (FALLBACK_STAGE, FALLBACK_CATEGORY).
    Never echoes an arbitrary exception string into the response. This
    fallback is defense in depth -- every ControlFailure this module itself
    raises already uses only allowed (stage, category) pairs -- not a
    designed pathway."""
    stage = failure.stage if isinstance(failure, ControlFailure) else None
    category = failure.category if isinstance(failure, ControlFailure) else None
    if (
        not isinstance(stage, str)
        or not isinstance(category, str)
        or stage not in ALLOWED_STAGE_CATEGORIES
        or category not in ALLOWED_STAGE_CATEGORIES[stage]
    ):
        stage, category = FALLBACK_STAGE, FALLBACK_CATEGORY
    return {
        "schema_version": 1,
        "request_id": request_id if _is_valid_request_id(request_id) else None,
        "tool_id": tool_id if _is_valid_tool_id(tool_id) else None,
        "status": "failure", "error": {"stage": stage, "category": category},
    }
