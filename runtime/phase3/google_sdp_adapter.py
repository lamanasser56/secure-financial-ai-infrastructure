"""Disabled Google SDP text candidate behind the neutral redactor boundary.

No production factory imports or constructs this adapter. The optional SDK is
loaded only when a caller explicitly constructs a real evaluation client.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from .trusted_runtime import RedactionResult


REGION = "me-central2"
ENDPOINT = "dlp.me-central2.rep.googleapis.com"
RPC_TIMEOUT_SECONDS = 20
_PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_INFO_TYPES = {
    "CREDIT_CARD_NUMBER": "CREDIT_CARD",
    "EMAIL_ADDRESS": "EMAIL_ADDRESS",
    "PHONE_NUMBER": "PHONE_NUMBER",
}


class GoogleSDPFailure(RuntimeError):
    """A fixed failure with no provider data or configuration detail."""

    def __init__(self):
        super().__init__("redaction:provider_failure")


def _guarded(operation: Callable[[], Any]) -> Any:
    """Discard provider exceptions, including their potentially sensitive context."""
    try:
        return operation()
    except Exception:
        pass
    raise GoogleSDPFailure()


def _create_client() -> Any:
    from google.cloud import dlp_v2  # Optional dependency; never imported by the core.

    # Omitted credentials select Application Default Credentials in the SDK.
    return dlp_v2.DlpServiceClient(client_options={"api_endpoint": ENDPOINT})


def _findings(response: Any, text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    found = list(response.result.findings)
    if len(found) > 1000:
        raise ValueError
    categories: set[str] = set()
    fragments: list[str] = []
    ranges: list[tuple[int, int]] = []
    for finding in found:
        category = _INFO_TYPES[finding.info_type.name]
        span = finding.location.codepoint_range
        start, end = span.start, span.end
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            raise ValueError
        categories.add(category)
        fragments.append(text[start:end])
        ranges.append((start, end))
    ordered = sorted(ranges)
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError
    return tuple(sorted(categories)), tuple(fragments)


def _output(response: Any) -> str:
    value = response.item.value
    if type(value) is not str or not value.strip():
        raise ValueError
    return value


class GoogleSDPRedactor:
    """Offline evaluation candidate; not connected to TrustedRuntime."""

    def __init__(
        self,
        project_id: str,
        *,
        endpoint: str = ENDPOINT,
        region: str = REGION,
        client: Any = None,
    ):
        if (
            type(project_id) is not str
            or _PROJECT_ID.fullmatch(project_id) is None
            or type(endpoint) is not str
            or endpoint != ENDPOINT
            or type(region) is not str
            or region != REGION
        ):
            raise GoogleSDPFailure()
        self._parent = f"projects/{project_id}/locations/{REGION}"
        self._operation_counts = {"inspect_attempted": 0, "deidentify_attempted": 0}
        self._client = client if client is not None else _guarded(_create_client)
        if _guarded(lambda: self._client.api_endpoint == ENDPOINT) is not True:
            raise GoogleSDPFailure()

    @property
    def operation_counts(self) -> dict[str, int]:
        """SDK invocation attempts; no request data and no server receipt claim."""
        return dict(self._operation_counts)

    def redact(self, text: str) -> RedactionResult:
        if type(text) is not str or not text.strip() or len(text) > 4000:
            raise GoogleSDPFailure()
        info_types = [{"name": name} for name in _INFO_TYPES]
        inspect_config = {"info_types": info_types, "include_quote": False}
        item = {"value": text}
        self._operation_counts["inspect_attempted"] += 1
        inspected = _guarded(lambda: self._client.inspect_content(
            request={"parent": self._parent, "item": item, "inspect_config": inspect_config},
            retry=None,
            timeout=RPC_TIMEOUT_SECONDS,
        ))
        categories, fragments = _guarded(lambda: _findings(inspected, text))
        self._operation_counts["deidentify_attempted"] += 1
        transformed = _guarded(lambda: self._client.deidentify_content(
            request={
                "parent": self._parent,
                "item": item,
                "inspect_config": inspect_config,
                "deidentify_config": {
                    "info_type_transformations": {
                        "transformations": [{
                            "primitive_transformation": {"replace_with_info_type_config": {}}
                        }]
                    }
                },
            },
            retry=None,
            timeout=RPC_TIMEOUT_SECONDS,
        ))
        redacted = _guarded(lambda: _output(transformed))
        if any(fragment in redacted for fragment in fragments):
            raise GoogleSDPFailure()
        if not fragments and redacted != text:
            raise GoogleSDPFailure()
        return RedactionResult(redacted, categories)
