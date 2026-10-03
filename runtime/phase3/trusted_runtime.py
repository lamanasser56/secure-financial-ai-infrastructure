"""Fail-closed Phase 3 orchestration with dependency-injected control clients."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Protocol


STAGES = (
    "authentication",
    "tenant_context",
    "authorization",
    "structured_input_validation",
    "agent_policy_engine",
    "presidio_analyzer",
    "presidio_anonymizer",
    "litellm",
    "provider",
    "structured_output_validation",
)
APPROVED_MODEL_ALIAS = "secure-financial-chat"
SUPPORTED_ENTITIES = {
    "CREDIT_CARD",
    "EMAIL_ADDRESS",
    "IBAN_CODE",
    "PHONE_NUMBER",
    "SAUDI_BANK_ACCOUNT",
    "SAUDI_NATIONAL_ID",
    "SAUDI_RESIDENT_ID",
    "SAUDI_VAT_ID",
}
REDACTION_STAGES = {"presidio_analyzer", "presidio_anonymizer"}
REDACTION_FAILURE_CATEGORIES = {
    "timeout", "unavailable", "malformed_result", "ambiguous_result", "incomplete_redaction"
}
TENANT_KEYS = {"tenant", "tenant_id", "tenantid", "tenant-id"}
TENANT_REF_PATTERN = re.compile(r"^[0-9a-f]{16}$")
CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class ControlFailure(Exception):
    """Sanitized failure from one required runtime control."""

    def __init__(self, stage: str, category: str):
        super().__init__(f"{stage}:{category}")
        self.stage = stage
        self.category = category


class RedactionFailure(ControlFailure):
    """Sanitized redaction failure carrying normalized category names."""

    def __init__(self, stage: str, category: str, categories: tuple[str, ...] = ()):
        super().__init__(stage, category)
        self.categories = categories


@dataclass(frozen=True)
class IdentityClaims:
    subject: str
    tenant_claim: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    tenant_ref: str


@dataclass(frozen=True)
class ValidatedInput:
    action: str
    message: str
    response_format: str


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason_code: str


@dataclass(frozen=True)
class GatewayResult:
    output: Any
    provider_called: bool
    execution_mode: str = "live"


@dataclass(frozen=True)
class RedactionResult:
    text: str
    categories: tuple[str, ...]


class Authenticator(Protocol):
    def authenticate(self, authorization: str) -> IdentityClaims: ...


class TenantResolver(Protocol):
    def resolve(self, claims: IdentityClaims) -> TenantContext: ...


class Authorizer(Protocol):
    def authorize(
        self, claims: IdentityClaims, tenant: TenantContext, action: str
    ) -> bool: ...


class PolicyEngine(Protocol):
    def evaluate(self, request: dict[str, Any]) -> PolicyDecision: ...


class RedactorClient(Protocol):
    def redact(self, text: str) -> RedactionResult: ...


class GatewayClient(Protocol):
    def complete(
        self, model_alias: str, redacted_text: str, metadata: dict[str, str]
    ) -> GatewayResult: ...


class TraceSink(Protocol):
    def emit(self, envelope: dict[str, Any]) -> None: ...


def _call(stage: str, operation):
    try:
        return operation()
    except ControlFailure:
        raise
    except TimeoutError as exc:
        raise ControlFailure(stage, "timeout") from exc
    except Exception as exc:
        raise ControlFailure(stage, "unavailable") from exc


def _valid_categories(value: Any) -> bool:
    return (
        isinstance(value, tuple)
        and all(type(item) is str and item in SUPPORTED_ENTITIES for item in value)
        and tuple(sorted(set(value))) == value
    )


def _call_redactor(redactor: RedactorClient, text: str) -> Any:
    """Keep a redactor's raw failure details behind bounded trace categories."""
    try:
        return redactor.redact(text)
    except RedactionFailure as failure:
        if (
            type(failure.stage) is not str
            or failure.stage not in REDACTION_STAGES
            or type(failure.category) is not str
            or failure.category not in REDACTION_FAILURE_CATEGORIES
            or not _valid_categories(failure.categories)
        ):
            raise ControlFailure("presidio_anonymizer", "malformed_result") from None
        raise RedactionFailure(failure.stage, failure.category, failure.categories) from None
    except ControlFailure as failure:
        if (
            type(failure.stage) is not str
            or failure.stage not in REDACTION_STAGES
            or type(failure.category) is not str
            or failure.category not in REDACTION_FAILURE_CATEGORIES
        ):
            raise ControlFailure("presidio_anonymizer", "malformed_result") from None
        raise ControlFailure(failure.stage, failure.category) from None
    except TimeoutError:
        raise ControlFailure("presidio_anonymizer", "timeout") from None
    except Exception:
        raise ControlFailure("presidio_anonymizer", "unavailable") from None


def _contains_tenant_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("_", "-")
            if normalized in TENANT_KEYS or normalized.replace("-", "") == "tenantid":
                return True
            if _contains_tenant_key(child):
                return True
    if isinstance(value, list):
        return any(_contains_tenant_key(item) for item in value)
    return False


def redact_checked(redactor: RedactorClient, text: str) -> RedactionResult:
    """Reuse the authoritative redactor and its closed result/failure contract."""
    redaction = _call_redactor(redactor, text)
    if (
        type(redaction) is not RedactionResult
        or not isinstance(redaction.text, str)
        or not redaction.text.strip()
        or not _valid_categories(redaction.categories)
    ):
        raise ControlFailure("presidio_anonymizer", "malformed_result")
    if redaction.categories and redaction.text == text:
        raise ControlFailure("presidio_anonymizer", "incomplete_redaction")
    return redaction


def is_valid_tenant_ref(value: Any) -> bool:
    """Accept only an already-created pseudonymous tenant reference."""
    return isinstance(value, str) and TENANT_REF_PATTERN.fullmatch(value) is not None


def validate_input(body: Any) -> ValidatedInput:
    if not isinstance(body, dict) or _contains_tenant_key(body):
        raise ControlFailure("structured_input_validation", "invalid_request")
    if set(body) != {"action", "input"} or body.get("action") != "chat.complete":
        raise ControlFailure("structured_input_validation", "invalid_request")
    content = body.get("input")
    if not isinstance(content, dict) or set(content) != {"message", "response_format"}:
        raise ControlFailure("structured_input_validation", "invalid_request")
    message = content.get("message")
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        raise ControlFailure("structured_input_validation", "invalid_request")
    if content.get("response_format") != "json":
        raise ControlFailure("structured_input_validation", "invalid_request")
    return ValidatedInput("chat.complete", message, "json")


def validate_output(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"summary", "classification"}:
        raise ControlFailure("structured_output_validation", "malformed_result")
    if not isinstance(value["summary"], str) or not value["summary"].strip() or len(value["summary"]) > 2000:
        raise ControlFailure("structured_output_validation", "malformed_result")
    if value["classification"] not in {"informational", "action_required"}:
        raise ControlFailure("structured_output_validation", "malformed_result")
    return {"summary": value["summary"], "classification": value["classification"]}


class TrustedRuntime:
    """Enforce the approved Phase 3 sequence with no bypass or fallback."""

    def __init__(
        self,
        authenticator: Authenticator,
        tenant_resolver: TenantResolver,
        authorizer: Authorizer,
        policy_engine: PolicyEngine,
        redactor: RedactorClient,
        gateway: GatewayClient,
        trace_sink: TraceSink,
        *,
        allow_offline_simulation: bool = False,
    ):
        if type(allow_offline_simulation) is not bool:
            raise ValueError("runtime:invalid_configuration")
        self.authenticator = authenticator
        self.tenant_resolver = tenant_resolver
        self.authorizer = authorizer
        self.policy_engine = policy_engine
        self.redactor = redactor
        self.gateway = gateway
        self.trace_sink = trace_sink
        self.allow_offline_simulation = allow_offline_simulation

    def execute(
        self, authorization: str, body: Any, correlation_id: str
    ) -> dict[str, Any]:
        if not isinstance(correlation_id, str) or not CORRELATION_PATTERN.fullmatch(correlation_id):
            raise ControlFailure("authentication", "invalid_correlation")
        stage = "authentication"
        tenant_ref = None
        subject_ref = None
        categories: list[str] = []
        provider_called = False
        try:
            claims = _call(stage, lambda: self.authenticator.authenticate(authorization))
            if not isinstance(claims, IdentityClaims) or not claims.subject or not claims.tenant_claim:
                raise ControlFailure(stage, "malformed_claims")
            subject_ref = hashlib.sha256(claims.subject.encode()).hexdigest()[:16]

            stage = "tenant_context"
            tenant = _call(stage, lambda: self.tenant_resolver.resolve(claims))
            if (
                not isinstance(tenant, TenantContext)
                or not tenant.tenant_id
                or not is_valid_tenant_ref(tenant.tenant_ref)
            ):
                raise ControlFailure(stage, "malformed_context")
            tenant_ref = tenant.tenant_ref

            stage = "authorization"
            allowed = _call(
                stage, lambda: self.authorizer.authorize(claims, tenant, "chat.complete")
            )
            if allowed is not True:
                raise ControlFailure(stage, "denied")

            stage = "structured_input_validation"
            validated = validate_input(body)

            stage = "agent_policy_engine"
            decision = _call(
                stage,
                lambda: self.policy_engine.evaluate(
                    {
                        "action": validated.action,
                        "message_length": len(validated.message),
                        "response_format": validated.response_format,
                        "redaction_required": True,
                    }
                ),
            )
            if not isinstance(decision, PolicyDecision):
                raise ControlFailure(stage, "malformed_decision")
            if decision.allowed is not True or decision.reason_code != "phase3_chat_allowed":
                raise ControlFailure(stage, "denied")

            # Preserve the existing trace stages while the concrete redactor
            # owns its internal analyzer/anonymizer sequence.
            stage = "presidio_anonymizer"
            redaction = redact_checked(self.redactor, validated.message)
            categories = list(redaction.categories)
            redacted = redaction.text

            stage = "litellm"
            gateway_result = _call(
                stage,
                lambda: self.gateway.complete(
                    APPROVED_MODEL_ALIAS,
                    redacted,
                    {"correlation_id": correlation_id, "tenant_ref": tenant.tenant_ref},
                ),
            )
            if not isinstance(gateway_result, GatewayResult):
                raise ControlFailure(stage, "malformed_result")
            live = (
                gateway_result.execution_mode == "live"
                and gateway_result.provider_called is True
            )
            simulated = (
                self.allow_offline_simulation
                and gateway_result.execution_mode == "offline_simulation"
                and gateway_result.provider_called is False
            )
            if not (live or simulated):
                raise ControlFailure(stage, "malformed_result")
            provider_called = gateway_result.provider_called

            stage = "structured_output_validation"
            output = validate_output(gateway_result.output)
            response = {
                "request_id": correlation_id,
                "model": APPROVED_MODEL_ALIAS,
                "result": output,
            }
            self._trace(
                correlation_id, tenant_ref, subject_ref, "success", None,
                "allowed", "completed", categories, provider_called, None,
            )
            return response
        except ControlFailure as failure:
            if isinstance(failure, RedactionFailure):
                categories = list(failure.categories)
            self._trace(
                correlation_id, tenant_ref, subject_ref, "blocked", failure.stage,
                "denied" if failure.stage in {"authorization", "agent_policy_engine"} else "not_reached",
                "failed" if failure.stage.startswith("presidio_") else "not_reached",
                categories, provider_called, failure.category,
            )
            raise

    def _trace(
        self,
        request_id: str,
        tenant_ref: str | None,
        subject_ref: str | None,
        outcome: str,
        failed_stage: str | None,
        policy_outcome: str,
        redaction_status: str,
        categories: list[str],
        provider_called: bool,
        error_category: str | None,
    ) -> None:
        envelope = {
            "schema_version": 1,
            "request_id": request_id,
            "tenant_ref": tenant_ref,
            "subject_ref": subject_ref,
            "outcome": outcome,
            "failed_stage": failed_stage,
            "policy_outcome": policy_outcome,
            "redaction_status": redaction_status,
            "detected_categories": categories,
            "model_alias": APPROVED_MODEL_ALIAS if provider_called else None,
            "provider_called": provider_called,
            "error_category": error_category,
        }
        try:
            self.trace_sink.emit(envelope)
        except Exception:
            pass
