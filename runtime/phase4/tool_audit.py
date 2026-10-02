"""Portfolio Phase 4C sanitized AI Audit Event contract."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from runtime.phase3.trusted_runtime import ControlFailure
from runtime.phase4.tool_policy import TOOL_POLICY_REASON_CODES, PolicyOutcome


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_REF_PATTERN = re.compile(r"^[0-9a-f]{16}$")
_TOOL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
_ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_RISK_CLASSES = {
    "low_risk_read", "sensitive_financial_read", "reversible_write",
    "irreversible_high_impact",
}
_INDICATORS = {
    "instruction_override", "policy_evasion", "tool_manipulation",
    "data_exfiltration",
}
_APPROVAL_RESULTS = {"not_required", "approved", "denied", "failed"}
_GOVERNANCE_RESULTS = {"qualified", "blocked"}
_FAILURE_PAIRS = {
    "prompt_injection_assessment": {
        "timeout", "unavailable", "malformed_assessment",
        "unsupported_indicator_category", "suspected_injection",
    },
    "agent_policy_engine": {
        "timeout", "unavailable", "denied", "malformed_decision",
        "argument_digest_failure",
    },
    "human_approval_verification": {
        "timeout", "unavailable", "missing_decision", "denied_decision",
        "expired_decision", "replayed_decision", "tenant_mismatch",
        "subject_mismatch", "tool_mismatch", "arguments_digest_mismatch",
        "malformed_decision",
    },
    "audit": {"invalid_event"},
}
_FIELDS = {
    "schema_version", "event_id", "event_type", "occurred_at", "request_id",
    "tenant_ref", "subject_ref", "tool_id", "tool_version", "required_action",
    "risk_classification", "authorization_result", "injection_result",
    "indicator_categories", "policy_outcome", "policy_reason_code",
    "approval_result", "governance_result", "failure_stage", "failure_category",
}


def _fail() -> None:
    raise ControlFailure("audit", "invalid_event")


def _format_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        _fail()
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_ai_audit_event(value: Any) -> dict[str, Any]:
    """Validate an allowlisted event; reject arbitrary or sensitive fields."""
    if not isinstance(value, dict) or set(value) != _FIELDS:
        _fail()
    try:
        occurred_at = datetime.fromisoformat(value["occurred_at"].replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError, OverflowError):
        _fail()
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        _fail()
    if (
        not isinstance(value["schema_version"], int)
        or isinstance(value["schema_version"], bool)
        or value["schema_version"] != 1
        or value["event_type"] != "tool_governance"
    ):
        _fail()
    if not isinstance(value["event_id"], str) or not _ID_PATTERN.fullmatch(value["event_id"]):
        _fail()
    if not isinstance(value["request_id"], str) or not _ID_PATTERN.fullmatch(value["request_id"]):
        _fail()
    if not isinstance(value["tenant_ref"], str) or not _REF_PATTERN.fullmatch(value["tenant_ref"]):
        _fail()
    if not isinstance(value["subject_ref"], str) or not _REF_PATTERN.fullmatch(value["subject_ref"]):
        _fail()
    if not isinstance(value["tool_id"], str) or not _TOOL_ID_PATTERN.fullmatch(value["tool_id"]):
        _fail()
    if not isinstance(value["tool_version"], str) or not _VERSION_PATTERN.fullmatch(value["tool_version"]):
        _fail()
    if not isinstance(value["required_action"], str) or not _ACTION_PATTERN.fullmatch(value["required_action"]):
        _fail()
    if value["risk_classification"] not in _RISK_CLASSES:
        _fail()
    if value["authorization_result"] != "allowed":
        _fail()
    if value["injection_result"] not in {"clear", "suspected", "failed"}:
        _fail()
    indicators = value["indicator_categories"]
    if (
        not isinstance(indicators, list)
        or any(item not in _INDICATORS for item in indicators)
        or len(indicators) != len(set(indicators))
    ):
        _fail()
    try:
        outcome = PolicyOutcome(value["policy_outcome"])
    except (TypeError, ValueError):
        _fail()
    if value["policy_reason_code"] not in TOOL_POLICY_REASON_CODES[outcome]:
        _fail()
    if value["approval_result"] not in _APPROVAL_RESULTS:
        _fail()
    if value["governance_result"] not in _GOVERNANCE_RESULTS:
        _fail()
    stage, category = value["failure_stage"], value["failure_category"]
    if value["governance_result"] == "qualified":
        if stage is not None or category is not None:
            _fail()
    elif (
        not isinstance(stage, str)
        or not isinstance(category, str)
        or stage not in _FAILURE_PAIRS
        or category not in _FAILURE_PAIRS[stage]
    ):
        _fail()
    return {
        key: list(item) if isinstance(item, list) else item
        for key, item in value.items()
    }


def build_ai_audit_event(
    *,
    event_id: str,
    occurred_at: datetime,
    request_id: str,
    tenant_ref: str,
    subject_ref: str,
    tool_id: str,
    tool_version: str,
    required_action: str,
    risk_classification: str,
    authorization_result: str,
    injection_result: str,
    indicator_categories: tuple[str, ...],
    policy_outcome: PolicyOutcome,
    policy_reason_code: str,
    approval_result: str,
    governance_result: str,
    failure: ControlFailure | None,
) -> dict[str, Any]:
    if not isinstance(policy_outcome, PolicyOutcome):
        _fail()
    if failure is not None and not isinstance(failure, ControlFailure):
        _fail()
    event = {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": "tool_governance",
        "occurred_at": _format_timestamp(occurred_at),
        "request_id": request_id,
        "tenant_ref": tenant_ref,
        "subject_ref": subject_ref,
        "tool_id": tool_id,
        "tool_version": tool_version,
        "required_action": required_action,
        "risk_classification": risk_classification,
        "authorization_result": authorization_result,
        "injection_result": injection_result,
        "indicator_categories": list(indicator_categories),
        "policy_outcome": policy_outcome.value,
        "policy_reason_code": policy_reason_code,
        "approval_result": approval_result,
        "governance_result": governance_result,
        "failure_stage": failure.stage if failure else None,
        "failure_category": failure.category if failure else None,
    }
    return validate_ai_audit_event(event)
