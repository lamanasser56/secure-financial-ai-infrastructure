"""Disabled Google SDP text candidate behind the neutral redactor boundary.

No production factory imports or constructs this adapter. The optional SDK is
loaded only when a caller explicitly constructs a real evaluation client.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
import math
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable
import unicodedata

from .trusted_runtime import RedactionResult


RPC_TIMEOUT_SECONDS = 3
OVERALL_TIMEOUT_SECONDS = 8
MAX_INPUT_BYTES = 4096
MAX_OUTPUT_BYTES = 4096
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


def _deployment() -> tuple[str, str]:
    """Read only the committed artifact contract, never request or environment data."""
    path = Path(__file__).resolve().parents[2] / "evaluation/google-sdp/deployment.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        type(value) is not dict
        or set(value) != {"schema_version", "region", "endpoint"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["region"] != "us-east1"
        or value["endpoint"] != "dlp.us-east1.rep.googleapis.com"
    ):
        raise ValueError
    return value["region"], value["endpoint"]


REGION, ENDPOINT = _guarded(_deployment)


def _create_client() -> Any:
    from google.cloud import dlp_v2  # Optional dependency; never imported by the core.

    # Omitted credentials select Application Default Credentials in the SDK.
    return dlp_v2.DlpServiceClient(client_options={"api_endpoint": ENDPOINT})


class ContentAttemptBudget:
    """Shared dispatch budget, including failed attempts; construction costs zero.

    A reservation admits both operations before inspection. Unused slots are
    released, but attempted operations are never refunded. Injected-client calls
    consume test slots, separately from SDK attempts. Share this object across
    candidate instances to prevent a conversation reset from renewing the budget.
    No runtime factory wires this candidate or budget into the agents yet.
    """

    def __init__(self, limit: int = 18):
        if type(limit) is not int or not 1 <= limit <= 174:
            raise GoogleSDPFailure()
        self.limit = limit
        self._used = self._reserved = 0
        self._lock = threading.Lock()

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    def reserve(self) -> "_Reservation":
        with self._lock:
            if self._used + self._reserved + 2 > self.limit:
                raise GoogleSDPFailure()
            self._reserved += 2
        return _Reservation(self)


class _Reservation:
    def __init__(self, budget: ContentAttemptBudget):
        self.budget, self.remaining = budget, 2

    def attempt(self) -> None:
        with self.budget._lock:
            if self.remaining <= 0:
                raise GoogleSDPFailure()
            self.remaining -= 1
            self.budget._reserved -= 1
            self.budget._used += 1

    def close(self) -> None:
        with self.budget._lock:
            self.budget._reserved -= self.remaining
            self.remaining = 0


@dataclass(frozen=True)
class InspectionSpan:
    """Private evaluation coordinates; never part of RedactionResult or traces."""

    start: int
    end: int
    info_type: str
    category_name: str | None = field(default=None, repr=False, compare=False)

    @property
    def category(self) -> str:
        return (
            self.category_name
            if self.category_name is not None
            else _INFO_TYPES[self.info_type]
        )


def _present(value: Any, field: str) -> bool:
    # Proto-plus uses proto3 message presence, not a nonzero start offset.
    protobuf = getattr(value, "_pb", None)
    return protobuf.HasField(field) if protobuf is not None else hasattr(value, field)


def inspection_spans(
    response: Any, text: str, allowed_types=None
) -> tuple[InspectionSpan, ...]:
    """Validate documented half-open Unicode offsets, cross-check UTF-8 bytes.

    This evaluation-only helper exposes coordinates to the in-memory scorer.
    Runtime callers receive only a neutral result, never spans or provider data.
    Byte-only, nested/table locations and ambiguous overlaps are rejected.
    """
    allowed_types = _INFO_TYPES if allowed_types is None else allowed_types
    if not _present(response, "result"):
        raise ValueError
    if response.result.findings_truncated is not False:
        raise ValueError
    found = list(response.result.findings)
    if len(found) > 1000:
        raise ValueError
    spans = []
    for finding in found:
        name = finding.info_type.name
        if name not in allowed_types or getattr(finding, "quote", ""):
            raise ValueError
        location = finding.location
        if not _present(location, "codepoint_range") or getattr(
            location, "content_locations", ()
        ):
            raise ValueError
        span = location.codepoint_range
        start, end = span.start, span.end
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(text)
        ):
            raise ValueError
        if _present(location, "byte_range"):
            byte_span = location.byte_range
            expected = (
                len(text[:start].encode("utf-8")),
                len(text[:end].encode("utf-8")),
            )
            if (
                type(byte_span.start) is not int
                or type(byte_span.end) is not int
                or (byte_span.start, byte_span.end) != expected
            ):
                raise ValueError
        spans.append(InspectionSpan(start, end, name, allowed_types[name]))
    ordered = tuple(
        sorted(spans, key=lambda value: (value.start, value.end, value.info_type))
    )
    if any(left.end > right.start for left, right in zip(ordered, ordered[1:])):
        raise ValueError
    return ordered


def _canonical(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return "".join(
        str(unicodedata.decimal(char)) if char.isdecimal() else char
        for char in value
        if unicodedata.category(char) != "Cf"
    )


def _output(
    response: Any, original: str, spans: tuple[InspectionSpan, ...], allowed_types=None
) -> str:
    allowed_types = _INFO_TYPES if allowed_types is None else allowed_types
    if not _present(response, "item"):
        raise ValueError
    protobuf = getattr(response.item, "_pb", None)
    if protobuf is not None and protobuf.WhichOneof("data_item") != "value":
        raise ValueError
    value = response.item.value
    if (
        type(value) is not str
        or not value.strip()
        or len(value.encode("utf-8")) > MAX_OUTPUT_BYTES
    ):
        raise ValueError
    # ReplaceWithInfoTypeConfig produces the bare type name, not [TYPE]. Exact
    # reconstruction preserves all allowed text and detects partial/extra changes.
    cursor, pieces = 0, []
    for span in spans:
        pieces.extend((original[cursor : span.start], span.info_type))
        cursor = span.end
    pieces.append(original[cursor:])
    if value != "".join(pieces):
        raise ValueError
    normalized = _canonical(value)
    if any(_canonical(original[span.start : span.end]) in normalized for span in spans):
        raise ValueError
    overview = response.overview
    total = overview.transformed_bytes
    summaries = list(overview.transformation_summaries)
    if (
        type(total) is not int
        or not 0 <= total <= MAX_INPUT_BYTES
        or len(summaries) > len(allowed_types)
    ):
        raise ValueError
    expected = Counter(span.info_type for span in spans)
    actual = Counter()
    byte_total = 0
    for summary in summaries:
        if (
            _present(summary, "field")
            or _present(summary, "record_suppress")
            or getattr(summary, "field_transformations", ())
        ):
            raise ValueError
        name = summary.info_type.name
        size = summary.transformed_bytes
        if (
            name not in expected
            or name in actual
            or type(size) is not int
            or not 0 < size <= MAX_INPUT_BYTES
        ):
            raise ValueError
        transformation = summary.transformation
        if not _present(transformation, "replace_with_info_type_config"):
            raise ValueError
        protobuf = getattr(transformation, "_pb", None)
        if (
            protobuf is not None
            and protobuf.WhichOneof("transformation") != "replace_with_info_type_config"
        ):
            raise ValueError
        results = list(summary.results)
        if len(results) != 1:
            raise ValueError
        result = results[0]
        # SUCCESS=1 in the locked proto; no warning/error detail is accepted.
        if (
            type(result.count) is not int
            or result.count <= 0
            or type(result.code) is bool
            or result.code != 1
            or result.details
        ):
            raise ValueError
        actual[name] = result.count
        byte_total += size
    if actual != expected or byte_total != total or (bool(spans) != (total > 0)):
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
        budget: ContentAttemptBudget | None = None,
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
        if budget is not None and type(budget) is not ContentAttemptBudget:
            raise GoogleSDPFailure()
        self._budget = budget if budget is not None else ContentAttemptBudget()
        self._operation_counts = {"inspect_attempted": 0, "deidentify_attempted": 0}
        self._test_counts = dict(self._operation_counts)
        self._real_sdk = client is None
        self._busy = threading.Lock()
        self._client = client if client is not None else _guarded(_create_client)
        if _guarded(lambda: self._client.api_endpoint == ENDPOINT) is not True:
            raise GoogleSDPFailure()

    @property
    def operation_counts(self) -> dict[str, int]:
        """SDK invocation attempts; no request data and no server receipt claim."""
        return dict(self._operation_counts)

    @property
    def injected_client_counts(self) -> dict[str, int]:
        """Offline transport invocations, explicitly not SDK/provider calls."""
        return dict(self._test_counts)

    @property
    def uses_real_sdk(self) -> bool:
        return self._real_sdk

    def redact(self, text: str) -> RedactionResult:
        # No provider exception context, invalid Unicode or response escapes.
        return _guarded(lambda: self._redact(text))

    def _redact(self, text: str) -> RedactionResult:
        started = time.monotonic()
        deadline = started + OVERALL_TIMEOUT_SECONDS
        if (
            type(text) is not str
            or not text.strip()
            or len(text.encode("utf-8")) > MAX_INPUT_BYTES
        ):
            raise GoogleSDPFailure()
        if not self._busy.acquire(blocking=False):
            raise GoogleSDPFailure()
        reservation = None
        try:
            reservation = self._budget.reserve()
            return self._sequence(text, deadline, reservation)
        finally:
            if reservation is not None:
                reservation.close()
            self._busy.release()

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            raise GoogleSDPFailure()
        return remaining

    def _invoke(
        self, name: str, request: dict, deadline: float, reservation: _Reservation
    ) -> Any:
        operation = getattr(self._client, name + "_content")
        if not callable(operation):
            raise GoogleSDPFailure()
        timeout = min(RPC_TIMEOUT_SECONDS, self._remaining(deadline))
        started = time.monotonic()
        reservation.attempt()
        counts = self._operation_counts if self._real_sdk else self._test_counts
        counts[name + "_attempted"] += 1
        result = operation(request=request, retry=None, timeout=timeout)
        if time.monotonic() - started >= timeout:
            raise GoogleSDPFailure()
        self._remaining(deadline)
        return result

    def _sequence(
        self, text: str, deadline: float, reservation: _Reservation
    ) -> RedactionResult:
        type_map = self._type_map()
        info_types = [{"name": name} for name in type_map]
        inspect_config = self._inspect_configuration()
        item = {"value": text}
        inspected = self._invoke(
            "inspect",
            {
                "parent": self._parent,
                "item": item,
                "inspect_config": inspect_config,
            },
            deadline,
            reservation,
        )
        spans = (
            inspection_spans(inspected, text)
            if type_map is _INFO_TYPES
            else inspection_spans(inspected, text, type_map)
        )
        self._remaining(deadline)
        transformed = self._invoke(
            "deidentify",
            {
                "parent": self._parent,
                "item": item,
                "inspect_config": inspect_config,
                "deidentify_config": {
                    "info_type_transformations": {
                        "transformations": [
                            {
                                "info_types": [info_type],
                                "primitive_transformation": {
                                    "replace_with_info_type_config": {}
                                },
                            }
                            for info_type in info_types
                        ]
                    }
                },
            },
            deadline,
            reservation,
        )
        redacted = (
            _output(transformed, text, spans)
            if type_map is _INFO_TYPES
            else _output(transformed, text, spans, type_map)
        )
        redacted = self._normalized_output(text, spans, redacted)
        if len(redacted.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise GoogleSDPFailure()
        self._remaining(deadline)
        return RedactionResult(
            redacted, tuple(sorted({type_map[span.info_type] for span in spans}))
        )

    def _type_map(self):
        return _INFO_TYPES

    def _inspect_configuration(self):
        return {
            "info_types": [{"name": name} for name in _INFO_TYPES],
            "include_quote": False,
            "min_likelihood": "POSSIBLE",
        }

    def _normalized_output(self, original, spans, validated_output):
        return validated_output
