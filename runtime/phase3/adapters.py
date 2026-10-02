"""Real HTTP adapters implementing the Phase 3 Protocol interfaces.

These adapters replace the mock transport in runtime/phase3/mocks.py with
real calls to the in-cluster Presidio Analyzer, Presidio Anonymizer, and
LiteLLM Services. trusted_runtime.py is not modified: every adapter here
implements the exact same Protocol interface the mocks already implement,
and every failure mode is left to propagate naturally so the existing
_call() wrapper in trusted_runtime.py classifies it (TimeoutError -> stage
"timeout", anything else -> stage "unavailable") without any adapter-side
exception translation.

Presidio's real /analyze and /anonymize responses carry extra fields
(analysis_explanation, recognition_metadata, items) beyond Portfolio's closed
internal contract. This module's job is to normalize those real responses
down to the closed shape trusted_runtime.py already enforces
(validate_analysis / validate_redaction) -- never to loosen that contract.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .trusted_runtime import GatewayResult

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
