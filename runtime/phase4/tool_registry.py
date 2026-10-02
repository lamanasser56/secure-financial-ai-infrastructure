"""Portfolio Phase 4A Tool Registry — structure, metadata, and risk classification.

Validates and resolves tool metadata only. Executes no tool, calls no external
system, and takes no financial action. Tool request/response JSON Schemas and
OpenAPI contracts are Phase 4B; the Policy Evaluation Interface extension,
prompt-injection handling, the human approval extension point, and the AI
audit event schema extension are Phase 4C. This module defines only the
structure those later Change Sets attach to.

Tenant identity is never handled here. Tenant context comes only from
authenticated claims through the existing Phase 3 TenantResolver/Authorizer
seam (runtime/phase3/trusted_runtime.py); tool argument schemas must reject
tenant-shaped fields once they exist in Phase 4B. This module has no tool
arguments to inspect yet and makes no tenant-enforcement claim of its own.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

DEFERRED_SCHEMA_MARKER = "deferred-phase-4b"

# Frozen for Phase 4A. Widening this enum later to add one approved external
# value is additive and non-breaking for existing registry data — that is
# the design answer for future external sources, not a reason to add a
# second field now. See docs/phase4/phase-4a-tool-registry-contract.md.
SOURCE_SYSTEMS = ("internal",)

ID_MIN_LENGTH, ID_MAX_LENGTH = 3, 64
NAME_MAX_LENGTH = 120
DESCRIPTION_MIN_LENGTH, DESCRIPTION_MAX_LENGTH = 40, 500
OWNER_MAX_LENGTH = 120
REF_MAX_LENGTH = 200
ACTION_MIN_LENGTH, ACTION_MAX_LENGTH = 3, 100
EXTENSION_POINT_MAX_LENGTH = 100
TIMEOUT_SECONDS_MIN, TIMEOUT_SECONDS_MAX = 1, 120
MAX_CALLS_PER_TURN_MIN, MAX_CALLS_PER_TURN_MAX = 1, 20

_AUDIT_CLASSIFICATIONS = ("standard", "sensitive", "high_sensitivity")


class RiskClass(str, Enum):
    """Financial-tooling risk tiers. Read-only is not assumed harmless."""

    LOW_RISK_READ = "low_risk_read"
    SENSITIVE_FINANCIAL_READ = "sensitive_financial_read"
    REVERSIBLE_WRITE = "reversible_write"
    IRREVERSIBLE_HIGH_IMPACT = "irreversible_high_impact"


class OperationType(str, Enum):
    READ = "read"
    WRITE = "write"


# Every risk tier maps to exactly one mechanical operation type.
RISK_TO_OPERATION = {
    RiskClass.LOW_RISK_READ: OperationType.READ,
    RiskClass.SENSITIVE_FINANCIAL_READ: OperationType.READ,
    RiskClass.REVERSIBLE_WRITE: OperationType.WRITE,
    RiskClass.IRREVERSIBLE_HIGH_IMPACT: OperationType.WRITE,
}

# Both write tiers require human approval. Neither may resolve as executable
# until Phase 4C provides a verified approval decision mechanism.
APPROVAL_REQUIRED_RISK_CLASSES = (RiskClass.REVERSIBLE_WRITE, RiskClass.IRREVERSIBLE_HIGH_IMPACT)


class RegistryFailure(Exception):
    """Sanitized fail-closed failure from registry loading or resolution.

    Every failure path in this module — malformed input, an unreadable file,
    an unknown tool, a tool that cannot yet execute — raises this with one of
    a fixed set of categories. No parser or filesystem exception is ever
    allowed to propagate to a caller unwrapped.
    """

    def __init__(self, category: str, tool_id: str | None = None):
        super().__init__(f"{category}:{tool_id or '-'}")
        self.category = category
        self.tool_id = tool_id


@dataclass(frozen=True)
class Authorization:
    required_action: str


@dataclass(frozen=True)
class Approval:
    required: bool
    extension_point_ref: str | None


@dataclass(frozen=True)
class ExecutionBoundary:
    timeout_seconds: int | None
    max_calls_per_turn: int | None


@dataclass(frozen=True)
class ToolMetadata:
    id: str
    name: str
    description: str
    version: str
    owner: str
    enabled: bool
    risk_classification: RiskClass
    operation_type: OperationType
    input_schema_ref: str
    output_schema_ref: str
    authorization: Authorization
    approval: Approval
    audit_classification: str
    source_system: str
    execution_boundary: ExecutionBoundary

    @property
    def has_deferred_schema(self) -> bool:
        return (
            self.input_schema_ref == DEFERRED_SCHEMA_MARKER
            or self.output_schema_ref == DEFERRED_SCHEMA_MARKER
        )


@dataclass(frozen=True)
class RegistryReadyToolPendingGovernance:
    """Registry-ready state whose governance controls remain pending.

    This is not an execution grant. It proves only that the tool exists,
    is enabled, and has real input and output schema references. Policy
    evaluation and any required approval have not completed.

    Only the complete Phase 4C coordinator may consume this package-internal
    state under the approved composition contract.
    """

    metadata: ToolMetadata


def _fail(category: str, tool_id: str | None = None) -> None:
    raise RegistryFailure(category, tool_id)


def _bounded_string(value: Any, min_length: int, max_length: int) -> bool:
    return isinstance(value, str) and min_length <= len(value) <= max_length


def _bounded_int(value: Any, minimum: int, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _schema_ref(value: Any) -> bool:
    return _bounded_string(value, 1, REF_MAX_LENGTH)


def validate_tool_metadata(value: Any) -> ToolMetadata:
    """Validates one registry entry against every bound the JSON Schema
    (contracts/phase4/tool-metadata.schema.json) also declares — including
    string length limits, numeric bounds, and the risk/operation/approval
    cross-field invariants. Raises RegistryFailure on any defect; never
    returns a partially-valid ToolMetadata."""
    if not isinstance(value, dict):
        _fail("malformed_metadata")

    required = {
        "id", "name", "description", "version", "owner", "enabled",
        "risk_classification", "operation_type", "input_schema_ref",
        "output_schema_ref", "authorization", "approval",
        "audit_classification", "source_system", "execution_boundary",
    }
    if set(value) != required:
        _fail("malformed_metadata", value.get("id") if isinstance(value.get("id"), str) else None)

    tool_id = value["id"]
    if (
        not isinstance(tool_id, str)
        or not ID_PATTERN.fullmatch(tool_id)
        or not _bounded_string(tool_id, ID_MIN_LENGTH, ID_MAX_LENGTH)
    ):
        _fail("malformed_metadata")

    if not _bounded_string(value["name"], 1, NAME_MAX_LENGTH):
        _fail("malformed_metadata", tool_id)
    if not _bounded_string(value["description"], DESCRIPTION_MIN_LENGTH, DESCRIPTION_MAX_LENGTH):
        _fail("malformed_metadata", tool_id)
    if not _bounded_string(value["owner"], 1, OWNER_MAX_LENGTH):
        _fail("malformed_metadata", tool_id)

    if not isinstance(value["version"], str) or not VERSION_PATTERN.fullmatch(value["version"]):
        _fail("malformed_metadata", tool_id)

    if not isinstance(value["enabled"], bool):
        _fail("malformed_metadata", tool_id)

    try:
        risk = RiskClass(value["risk_classification"])
    except ValueError:
        _fail("unsupported_risk_class", tool_id)

    try:
        operation = OperationType(value["operation_type"])
    except ValueError:
        _fail("malformed_metadata", tool_id)

    if operation != RISK_TO_OPERATION[risk]:
        _fail("malformed_metadata", tool_id)

    if not _schema_ref(value["input_schema_ref"]):
        _fail("malformed_metadata", tool_id)
    if not _schema_ref(value["output_schema_ref"]):
        _fail("malformed_metadata", tool_id)

    authorization = value["authorization"]
    if (
        not isinstance(authorization, dict)
        or set(authorization) != {"required_action"}
        or not isinstance(authorization["required_action"], str)
        or not ACTION_PATTERN.fullmatch(authorization["required_action"])
        or not _bounded_string(authorization["required_action"], ACTION_MIN_LENGTH, ACTION_MAX_LENGTH)
    ):
        _fail("missing_authorization", tool_id)

    approval = value["approval"]
    if (
        not isinstance(approval, dict)
        or set(approval) != {"required", "extension_point_ref"}
        or not isinstance(approval["required"], bool)
        or not (
            approval["extension_point_ref"] is None
            or _bounded_string(approval["extension_point_ref"], 1, EXTENSION_POINT_MAX_LENGTH)
        )
    ):
        _fail("malformed_metadata", tool_id)
    if risk in APPROVAL_REQUIRED_RISK_CLASSES and approval["required"] is not True:
        _fail("malformed_metadata", tool_id)
    if approval["required"] and not approval["extension_point_ref"]:
        _fail("malformed_metadata", tool_id)

    if value["audit_classification"] not in _AUDIT_CLASSIFICATIONS:
        _fail("malformed_metadata", tool_id)

    if value["source_system"] not in SOURCE_SYSTEMS:
        _fail("malformed_metadata", tool_id)

    boundary = value["execution_boundary"]
    if not isinstance(boundary, dict) or set(boundary) != {"timeout_seconds", "max_calls_per_turn"}:
        _fail("malformed_metadata", tool_id)
    timeout = boundary["timeout_seconds"]
    if timeout is not None and not _bounded_int(timeout, TIMEOUT_SECONDS_MIN, TIMEOUT_SECONDS_MAX):
        _fail("malformed_metadata", tool_id)
    max_calls = boundary["max_calls_per_turn"]
    if max_calls is not None and not _bounded_int(max_calls, MAX_CALLS_PER_TURN_MIN, MAX_CALLS_PER_TURN_MAX):
        _fail("malformed_metadata", tool_id)

    return ToolMetadata(
        id=tool_id, name=value["name"], description=value["description"], version=value["version"],
        owner=value["owner"], enabled=value["enabled"], risk_classification=risk,
        operation_type=operation, input_schema_ref=value["input_schema_ref"],
        output_schema_ref=value["output_schema_ref"],
        authorization=Authorization(authorization["required_action"]),
        approval=Approval(approval["required"], approval["extension_point_ref"]),
        audit_classification=value["audit_classification"], source_system=value["source_system"],
        execution_boundary=ExecutionBoundary(timeout, max_calls),
    )


def load_registry(path: str | Path) -> dict[str, ToolMetadata]:
    """Loads and validates a registry file. Every failure mode — a missing
    file, an unreadable file, invalid JSON, or a structurally invalid
    envelope — is normalized to a sanitized RegistryFailure; no raw
    OSError/UnicodeDecodeError/json.JSONDecodeError ever propagates."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        _fail("registry_unreadable")

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        _fail("registry_unreadable")

    if (
        not isinstance(raw, dict)
        or set(raw) != {"schema_version", "tools"}
        or not isinstance(raw.get("schema_version"), int)
        or isinstance(raw.get("schema_version"), bool)
        or raw.get("schema_version") != 1
    ):
        _fail("malformed_metadata")
    tools_raw = raw["tools"]
    if not isinstance(tools_raw, list) or not tools_raw:
        _fail("malformed_metadata")

    registry: dict[str, ToolMetadata] = {}
    for entry in tools_raw:
        tool = validate_tool_metadata(entry)
        if tool.id in registry:
            _fail("malformed_metadata", tool.id)
        registry[tool.id] = tool
    return registry


def get_tool_metadata(registry: dict[str, ToolMetadata], tool_id: str) -> ToolMetadata:
    """Unconditional structural lookup. Returns metadata for any registered
    tool regardless of enabled/approval/schema state — for introspection and
    registry listing only. This is NOT an execution or authorization check;
    use resolve_tool_preconditions for that."""
    if not isinstance(tool_id, str) or tool_id not in registry:
        _fail("unknown_tool", tool_id if isinstance(tool_id, str) else None)
    return registry[tool_id]


def _resolve_registry_readiness_for_governance(
    registry: dict[str, ToolMetadata],
    tool_id: str,
) -> RegistryReadyToolPendingGovernance:
    """Package-internal registry-readiness check for Phase 4C.

    Approval is deliberately not evaluated here because it is a governance
    control, not a static registry-readiness property. The distinct return
    type explicitly remains pending governance.
    """
    tool = get_tool_metadata(registry, tool_id)
    if not tool.enabled:
        _fail("disabled_tool", tool_id)
    if tool.has_deferred_schema:
        _fail("schema_deferred", tool_id)
    return RegistryReadyToolPendingGovernance(metadata=tool)


def resolve_tool_preconditions(registry: dict[str, ToolMetadata], tool_id: str) -> ToolMetadata:
    """Checks the Phase-4A-known preconditions for a tool to eventually be
    executable: it must exist, be enabled, have real (non-deferred) input and
    output schemas, and not require an approval decision that no mechanism
    yet exists to make.

    A successful return here means registry-resolution preconditions are
    satisfied — nothing more. It is NOT authorization, NOT a policy decision,
    NOT schema validation of a real request, and NOT permission to execute.
    Authentication, Tenant Context resolution, Authorization/Policy Engine
    evaluation (the Phase 3 seam, extended in Phase 4C), Structured
    Input/Output Validation against the tool's real Phase 4B schemas, and —
    where required — an approved Phase 4C approval decision must all
    separately succeed before any tool may actually run. No caller may treat
    this function's return value as an execution grant.
    """
    pending = _resolve_registry_readiness_for_governance(registry, tool_id)
    tool = pending.metadata
    if tool.approval.required:
        _fail("approval_required_no_decision", tool_id)
    return tool
