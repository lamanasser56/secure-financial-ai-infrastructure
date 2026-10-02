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
TENANT_KEYS = {"tenant", "tenant_id", "tenantid", "tenant-id"}
CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class ControlFailure(Exception):
    """Sanitized failure from one required runtime control."""

    def __init__(self, stage: str, category: str):
        super().__init__(f"{stage}:{category}")
        self.stage = stage
        self.category = category


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


class AnalyzerClient(Protocol):
    def analyze(self, text: str) -> Any: ...


class AnonymizerClient(Protocol):
    def anonymize(self, text: str, analyzer_results: list[dict[str, Any]]) -> Any: ...


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


def validate_analysis(value: Any, text_length: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ControlFailure("presidio_analyzer", "malformed_result")
    normalized = []
    spans = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"entity_type", "start", "end", "score"}:
            raise ControlFailure("presidio_analyzer", "malformed_result")
        entity = item["entity_type"]
        start, end, score = item["start"], item["end"], item["score"]
        if (
            entity not in SUPPORTED_ENTITIES
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not 0 <= start < end <= text_length
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not 0 <= score <= 1
            or (start, end) in spans
        ):
            raise ControlFailure("presidio_analyzer", "malformed_result")
        spans.add((start, end))
        normalized.append(dict(item))
    ordered = sorted(normalized, key=lambda item: (item["start"], item["end"]))
    if any(left["end"] > right["start"] for left, right in zip(ordered, ordered[1:])):
        raise ControlFailure("presidio_analyzer", "ambiguous_result")
    return ordered


def validate_redaction(original: str, result: Any, spans: list[dict[str, Any]]) -> str:
    if not isinstance(result, dict) or set(result) != {"text"} or not isinstance(result["text"], str):
        raise ControlFailure("presidio_anonymizer", "malformed_result")
    transformed = result["text"]
    for span in spans:
        protected = original[span["start"] : span["end"]]
        if protected and protected in transformed:
            raise ControlFailure("presidio_anonymizer", "incomplete_redaction")
    return transformed


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
        analyzer: AnalyzerClient,
        anonymizer: AnonymizerClient,
        gateway: GatewayClient,
        trace_sink: TraceSink,
    ):
        self.authenticator = authenticator
        self.tenant_resolver = tenant_resolver
        self.authorizer = authorizer
        self.policy_engine = policy_engine
        self.analyzer = analyzer
        self.anonymizer = anonymizer
        self.gateway = gateway
        self.trace_sink = trace_sink

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
            if not isinstance(tenant, TenantContext) or not tenant.tenant_id or not tenant.tenant_ref:
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

            stage = "presidio_analyzer"
            raw_analysis = _call(stage, lambda: self.analyzer.analyze(validated.message))
            analysis = validate_analysis(raw_analysis, len(validated.message))
            categories = sorted({item["entity_type"] for item in analysis})

            stage = "presidio_anonymizer"
            raw_redaction = _call(
                stage, lambda: self.anonymizer.anonymize(validated.message, analysis)
            )
            redacted = validate_redaction(validated.message, raw_redaction, analysis)

            stage = "litellm"
            gateway_result = _call(
                stage,
                lambda: self.gateway.complete(
                    APPROVED_MODEL_ALIAS,
                    redacted,
                    {"correlation_id": correlation_id, "tenant_ref": tenant.tenant_ref},
                ),
            )
            if not isinstance(gateway_result, GatewayResult) or gateway_result.provider_called is not True:
                raise ControlFailure(stage, "malformed_result")
            provider_called = True

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
