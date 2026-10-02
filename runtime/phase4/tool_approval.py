"""Portfolio Phase 4C human-approval extension-point contract."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from runtime.phase3.trusted_runtime import ControlFailure


APPROVAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
MAX_FUTURE_ISSUED_SKEW = timedelta(minutes=5)
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REF_PATTERN = re.compile(r"^[0-9a-f]{16}$")
_TOOL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
_ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_RISK_CLASSES = {
    "low_risk_read",
    "sensitive_financial_read",
    "reversible_write",
    "irreversible_high_impact",
}


@dataclass(frozen=True)
class ApprovalContext:
    request_id: str
    tenant_ref: str
    subject_ref: str
    tool_id: str
    tool_version: str
    required_action: str
    risk_classification: str
    arguments_digest: str


@dataclass(frozen=True)
class ApprovalDecision:
    approval_id: str
    decision: str
    request_id: str
    tenant_ref: str
    subject_ref: str
    tool_id: str
    tool_version: str
    required_action: str
    risk_classification: str
    arguments_digest: str
    issued_at: datetime
    expires_at: datetime
    consumed: bool


class ApprovalVerifier(Protocol):
    def retrieve_verified(self, approval_id: str) -> Any: ...


def canonical_arguments_digest(arguments: dict[str, Any]) -> str:
    try:
        canonical = json.dumps(
            arguments,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ControlFailure("agent_policy_engine", "argument_digest_failure") from exc


def _parse_aware_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone")
    return parsed.astimezone(timezone.utc)


def _normalize_decision(value: Any) -> ApprovalDecision:
    required = {
        "schema_version", "approval_id", "decision", "request_id",
        "tenant_ref", "subject_ref", "tool_id", "tool_version",
        "required_action", "risk_classification", "arguments_digest",
        "issued_at", "expires_at", "consumed",
    }
    try:
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("shape")
        if (
            not isinstance(value["schema_version"], int)
            or isinstance(value["schema_version"], bool)
            or value["schema_version"] != 1
        ):
            raise ValueError("version")
        if not isinstance(value["approval_id"], str) or not APPROVAL_ID_PATTERN.fullmatch(value["approval_id"]):
            raise ValueError("approval_id")
        if value["decision"] not in {"approved", "denied"}:
            raise ValueError("decision")
        if not isinstance(value["request_id"], str) or not APPROVAL_ID_PATTERN.fullmatch(value["request_id"]):
            raise ValueError("request_id")
        if not isinstance(value["tenant_ref"], str) or not _REF_PATTERN.fullmatch(value["tenant_ref"]):
            raise ValueError("tenant_ref")
        if not isinstance(value["subject_ref"], str) or not _REF_PATTERN.fullmatch(value["subject_ref"]):
            raise ValueError("subject_ref")
        if not isinstance(value["tool_id"], str) or not _TOOL_ID_PATTERN.fullmatch(value["tool_id"]):
            raise ValueError("tool_id")
        if not isinstance(value["tool_version"], str) or not _VERSION_PATTERN.fullmatch(value["tool_version"]):
            raise ValueError("tool_version")
        if not isinstance(value["required_action"], str) or not _ACTION_PATTERN.fullmatch(value["required_action"]):
            raise ValueError("required_action")
        if value["risk_classification"] not in _RISK_CLASSES:
            raise ValueError("risk")
        if not isinstance(value["arguments_digest"], str) or not _DIGEST_PATTERN.fullmatch(value["arguments_digest"]):
            raise ValueError("digest")
        if not isinstance(value["consumed"], bool):
            raise ValueError("consumed")
        issued_at = _parse_aware_timestamp(value["issued_at"])
        expires_at = _parse_aware_timestamp(value["expires_at"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ControlFailure("human_approval_verification", "malformed_decision") from exc
    return ApprovalDecision(
        approval_id=value["approval_id"], decision=value["decision"],
        request_id=value["request_id"], tenant_ref=value["tenant_ref"],
        subject_ref=value["subject_ref"], tool_id=value["tool_id"],
        tool_version=value["tool_version"], required_action=value["required_action"],
        risk_classification=value["risk_classification"],
        arguments_digest=value["arguments_digest"], issued_at=issued_at,
        expires_at=expires_at, consumed=value["consumed"],
    )


def verify_tool_approval(
    verifier: ApprovalVerifier,
    approval_id: str | None,
    context: ApprovalContext,
    *,
    now: datetime,
) -> ApprovalDecision:
    if not isinstance(approval_id, str) or not APPROVAL_ID_PATTERN.fullmatch(approval_id):
        raise ControlFailure("human_approval_verification", "missing_decision")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ControlFailure("human_approval_verification", "malformed_decision")
    now_utc = now.astimezone(timezone.utc)
    try:
        raw = verifier.retrieve_verified(approval_id)
    except ControlFailure as exc:
        if exc.stage == "human_approval_verification" and exc.category in {
            "timeout", "unavailable"
        }:
            raise
        raise ControlFailure("human_approval_verification", "unavailable") from exc
    except TimeoutError as exc:
        raise ControlFailure("human_approval_verification", "timeout") from exc
    except Exception as exc:
        raise ControlFailure("human_approval_verification", "unavailable") from exc

    decision = _normalize_decision(raw)
    if decision.approval_id != approval_id:
        raise ControlFailure("human_approval_verification", "malformed_decision")
    if decision.decision != "approved":
        raise ControlFailure("human_approval_verification", "denied_decision")
    if decision.consumed:
        raise ControlFailure("human_approval_verification", "replayed_decision")
    if decision.issued_at >= decision.expires_at:
        raise ControlFailure("human_approval_verification", "malformed_decision")
    if decision.issued_at > now_utc + MAX_FUTURE_ISSUED_SKEW:
        raise ControlFailure("human_approval_verification", "malformed_decision")
    if now_utc >= decision.expires_at:
        raise ControlFailure("human_approval_verification", "expired_decision")
    if decision.tenant_ref != context.tenant_ref:
        raise ControlFailure("human_approval_verification", "tenant_mismatch")
    if decision.subject_ref != context.subject_ref:
        raise ControlFailure("human_approval_verification", "subject_mismatch")
    if (
        decision.request_id != context.request_id
        or decision.tool_id != context.tool_id
        or decision.tool_version != context.tool_version
        or decision.required_action != context.required_action
        or decision.risk_classification != context.risk_classification
    ):
        raise ControlFailure("human_approval_verification", "tool_mismatch")
    if decision.arguments_digest != context.arguments_digest:
        raise ControlFailure(
            "human_approval_verification", "arguments_digest_mismatch"
        )
    return decision
