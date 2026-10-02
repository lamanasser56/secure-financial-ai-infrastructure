"""Real HTTP adapters implementing the Phase 3 Protocol interfaces.

These adapters call the in-cluster Presidio Analyzer, Presidio Anonymizer, and
LiteLLM Services. PresidioRedactor owns response validation and exposes only
the provider-neutral RedactorClient result to the trusted runtime.

Presidio's real /analyze and /anonymize responses carry extra fields
(analysis_explanation, recognition_metadata, items) beyond Portfolio's closed
internal contract. This module's job is to normalize those real responses
down to the closed shape validated here -- never to loosen that contract.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

from .trusted_runtime import (
    ControlFailure,
    GatewayResult,
    RedactionFailure,
    RedactionResult,
    SUPPORTED_ENTITIES,
)

DEFAULT_ANALYZER_URL = "http://presidio-analyzer.ai-platform.svc.cluster.local:3000/analyze"
DEFAULT_ANONYMIZER_URL = "http://presidio-anonymizer.ai-platform.svc.cluster.local:3000/anonymize"
DEFAULT_PRESIDIO_TIMEOUT_SECONDS = 10.0
# LiteLLM's configured provider timeout is 30s in
# kubernetes/apps/litellm/configmap.yaml. Stay above that so LiteLLM can
# report its own timeout before this adapter cuts the connection.
DEFAULT_LITELLM_TIMEOUT_SECONDS = 35.0
CLIENT_KEY_ENV_VAR = "PORTFOLIO_LITELLM_CLIENT_KEY"
BASE_URL_ENV_VAR = "PORTFOLIO_LITELLM_BASE_URL"
_DNS_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

_ANALYZER_RESULT_KEYS = ("entity_type", "start", "end", "score")

_OUTPUT_INSTRUCTION = (
    "Respond with a single JSON object and nothing else, using exactly these "
    'two keys: "summary" (a string) and "classification" (one of '
    '"informational" or "action_required"). Do not include any other keys, '
    "markdown formatting, or explanatory text."
)


def _post_json(
    url: str, payload: dict[str, Any], timeout: float, headers: dict[str, str] | None = None
) -> Any:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected status {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _project_analyzer_result(raw_item: Any) -> dict[str, Any]:
    return {key: raw_item[key] for key in _ANALYZER_RESULT_KEYS}


class HttpPresidioAnalyzer:
    """Real AnalyzerClient implementation calling Presidio Analyzer's /analyze."""

    def __init__(
        self,
        url: str = DEFAULT_ANALYZER_URL,
        timeout: float = DEFAULT_PRESIDIO_TIMEOUT_SECONDS,
        language: str = "en",
    ):
        self._url = url
        self._timeout = timeout
        self._language = language
        self.call_count = 0

    def analyze(self, text: str) -> Any:
        self.call_count += 1
        response = _post_json(self._url, {"text": text, "language": self._language}, self._timeout)
        return [_project_analyzer_result(item) for item in response]


class HttpPresidioAnonymizer:
    """Real AnonymizerClient implementation calling Presidio Anonymizer's /anonymize."""

    def __init__(self, url: str = DEFAULT_ANONYMIZER_URL, timeout: float = DEFAULT_PRESIDIO_TIMEOUT_SECONDS):
        self._url = url
        self._timeout = timeout
        self.call_count = 0

    def anonymize(self, text: str, analyzer_results: list[dict[str, Any]]) -> Any:
        self.call_count += 1
        response = _post_json(
            self._url,
            {"text": text, "analyzer_results": analyzer_results},
            self._timeout,
        )
        return {"text": response["text"]}


class AnalyzerClient(Protocol):
    def analyze(self, text: str) -> Any: ...


class AnonymizerClient(Protocol):
    def anonymize(self, text: str, analyzer_results: list[dict[str, Any]]) -> Any: ...


def _validate_analysis(value: Any, text_length: int) -> list[dict[str, Any]]:
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


def _validate_redaction(original: str, result: Any, spans: list[dict[str, Any]]) -> str:
    if not isinstance(result, dict) or set(result) != {"text"} or not isinstance(result["text"], str):
        raise ControlFailure("presidio_anonymizer", "malformed_result")
    transformed = result["text"]
    if not transformed.strip():
        raise ControlFailure("presidio_anonymizer", "malformed_result")
    for span in spans:
        protected = original[span["start"] : span["end"]]
        if protected and protected in transformed:
            raise ControlFailure("presidio_anonymizer", "incomplete_redaction")
    return transformed


class PresidioRedactor:
    """The sole concrete redactor: Analyze, validate, Anonymize, validate."""

    def __init__(
        self,
        analyzer: AnalyzerClient | None = None,
        anonymizer: AnonymizerClient | None = None,
    ):
        self.analyzer = analyzer if analyzer is not None else HttpPresidioAnalyzer()
        self.anonymizer = anonymizer if anonymizer is not None else HttpPresidioAnonymizer()

    def redact(self, text: str) -> RedactionResult:
        try:
            raw_analysis = self.analyzer.analyze(text)
        except TimeoutError:
            raise ControlFailure("presidio_analyzer", "timeout") from None
        except Exception:
            raise ControlFailure("presidio_analyzer", "unavailable") from None
        analysis = _validate_analysis(raw_analysis, len(text))
        categories = tuple(sorted({item["entity_type"] for item in analysis}))

        try:
            raw_redaction = self.anonymizer.anonymize(text, analysis)
        except TimeoutError:
            raise RedactionFailure("presidio_anonymizer", "timeout", categories) from None
        except Exception:
            raise RedactionFailure("presidio_anonymizer", "unavailable", categories) from None
        try:
            redacted = _validate_redaction(text, raw_redaction, analysis)
        except ControlFailure as failure:
            raise RedactionFailure(failure.stage, failure.category, categories) from None
        return RedactionResult(redacted, categories)


class GatewayConfigurationError(ValueError):
    """A fixed, non-sensitive failure for invalid gateway startup configuration."""

    def __init__(self):
        super().__init__("litellm:invalid_configuration")


def _validated_litellm_base_url(value: str | None) -> str:
    if not isinstance(value, str) or not value or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 or char == "\\"
        for char in value
    ) or "?" in value or "#" in value:
        raise GatewayConfigurationError()
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or "%" in parsed.netloc
            or port == 0
        ):
            raise GatewayConfigurationError()
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            if any(not _DNS_LABEL.fullmatch(label) for label in hostname.split(".")):
                raise GatewayConfigurationError() from None
    except ValueError:
        raise GatewayConfigurationError() from None
    return value.rstrip("/")


class HttpLiteLLMGateway:
    """Real GatewayClient implementation calling LiteLLM's /chat/completions.

    Trusted startup configuration supplies the endpoint and scoped client key.
    Neither request content nor metadata can replace either value.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = DEFAULT_LITELLM_TIMEOUT_SECONDS,
    ):
        configured_url = base_url if base_url is not None else os.environ.get(BASE_URL_ENV_VAR)
        self._url = _validated_litellm_base_url(configured_url) + "/chat/completions"
        client_key = os.environ.get(CLIENT_KEY_ENV_VAR)
        if (
            not isinstance(client_key, str)
            or not client_key.strip()
            or client_key != client_key.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in client_key)
        ):
            raise GatewayConfigurationError()
        self._authorization = "Bearer " + client_key
        self._timeout = timeout
        self.call_count = 0

    def complete(self, model_alias: str, redacted_text: str, metadata: dict[str, str]) -> GatewayResult:
        self.call_count += 1
        payload = {
            "model": model_alias,
            "messages": [
                {"role": "system", "content": _OUTPUT_INSTRUCTION},
                {"role": "user", "content": redacted_text},
            ],
            "response_format": {"type": "json_object"},
            "metadata": {
                "correlation_id": metadata.get("correlation_id"),
                "tenant_ref": metadata.get("tenant_ref"),
            },
        }
        response = _post_json(
            self._url,
            payload,
            self._timeout,
            headers={"Authorization": self._authorization},
        )
        content = response["choices"][0]["message"]["content"]
        try:
            parsed: Any = json.loads(content)
        except json.JSONDecodeError:
            # Pass the raw, non-JSON model text through unchanged.
            # validate_output() in trusted_runtime.py will correctly reject
            # it (isinstance(value, dict) is False) -- this is a deliberate
            # fail-closed path, not a contract weakening.
            parsed = content
        return GatewayResult(output=parsed, provider_called=True)
