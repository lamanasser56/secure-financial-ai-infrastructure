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
DIAGNOSTIC_CODES = frozenset({
    "UNKNOWN", "INVALID_INPUT", "CONFIGURATION_REJECTED", "BUSY",
    "BUDGET_EXHAUSTED", "RPC_TIMEOUT", "OVERALL_TIMEOUT", "RPC_STATUS",
    "RPC_FAILURE", "MALFORMED_RESPONSE", "INCOMPLETE_TRANSFORMATION",
    "OUTPUT_MISMATCH", "RESIDUAL_VALUE", "OUTPUT_LIMIT",
})
DIAGNOSTIC_STAGES = frozenset({
    "startup", "input", "budget", "inspect", "inspect_response",
    "deidentify", "output", "normalize", "sequence",
})
RPC_STATUSES = frozenset({
    "CANCELLED", "UNKNOWN", "INVALID_ARGUMENT", "DEADLINE_EXCEEDED",
    "NOT_FOUND", "ALREADY_EXISTS", "PERMISSION_DENIED", "UNAUTHENTICATED",
    "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION", "ABORTED", "OUT_OF_RANGE",
    "UNIMPLEMENTED", "INTERNAL", "UNAVAILABLE", "DATA_LOSS",
})


class GoogleSDPFailure(RuntimeError):
    """Fixed public error; evaluation diagnostics contain finite constants only."""

    def __init__(self, code="UNKNOWN", stage="startup", rpc_status=None):
        super().__init__("redaction:provider_failure")
        self._code = code if type(code) is str and code in DIAGNOSTIC_CODES else "UNKNOWN"
        self._stage = (
            stage if type(stage) is str and stage in DIAGNOSTIC_STAGES else "startup"
        )
        self._rpc_status = (
            rpc_status if type(rpc_status) is str and rpc_status in RPC_STATUSES else None
        )

    @property
    def diagnostic(self):
        value = {"code": self._code, "stage": self._stage}
        if self._rpc_status is not None:
            value["rpc_status"] = self._rpc_status
        return value


def _guarded(operation: Callable[[], Any], *, code="UNKNOWN", stage="startup") -> Any:
    """Discard provider exceptions, including their potentially sensitive context."""
    try:
        return operation()
    except Exception as error:
        diagnostic = (
            error.diagnostic if type(error) is GoogleSDPFailure
            else {"code": code, "stage": stage}
        )
    # Raise outside the handler: no raw exception context/cause is retained.
    raise GoogleSDPFailure(**diagnostic)


def _rpc_guarded(operation, stage):
    """Never serialize exceptions, status messages, metadata or response bodies."""
    try:
        return operation()
    except Exception as error:
        diagnostic = {"code": "RPC_FAILURE", "stage": stage}
        if isinstance(error, TimeoutError):
            diagnostic["code"] = "RPC_TIMEOUT"
        else:
            try:
                from google.api_core import exceptions
            except ImportError:
                exceptions = None
            if exceptions is not None and isinstance(error, exceptions.GoogleAPICallError):
                # Read the trusted exception CLASS's enum; no message or code() call.
                status = getattr(type(error), "grpc_status_code", None)
                name = getattr(status, "name", None)
                diagnostic.update(code="RPC_STATUS", rpc_status=(
                    name if type(name) is str and name in RPC_STATUSES else "UNKNOWN"
                ))
                if isinstance(error, exceptions.DeadlineExceeded):
                    diagnostic["code"] = "RPC_TIMEOUT"
    raise GoogleSDPFailure(**diagnostic)


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
                raise GoogleSDPFailure("BUDGET_EXHAUSTED", "budget")
            self._reserved += 2
        return _Reservation(self)


class _Reservation:
    def __init__(self, budget: ContentAttemptBudget):
        self.budget, self.remaining = budget, 2

    def attempt(self) -> None:
        with self.budget._lock:
            if self.remaining <= 0:
                raise GoogleSDPFailure("BUDGET_EXHAUSTED", "budget")
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
        raise GoogleSDPFailure("MALFORMED_RESPONSE", "output")
    protobuf = getattr(response.item, "_pb", None)
    if protobuf is not None and protobuf.WhichOneof("data_item") != "value":
        raise GoogleSDPFailure("MALFORMED_RESPONSE", "output")
    value = response.item.value
    if (
        type(value) is not str
        or not value.strip()
        or len(value.encode("utf-8")) > MAX_OUTPUT_BYTES
    ):
        code = (
            "OUTPUT_LIMIT"
            if type(value) is str and len(value.encode("utf-8")) > MAX_OUTPUT_BYTES
            else "MALFORMED_RESPONSE"
        )
        raise GoogleSDPFailure(code, "output")
    # Official REST examples use [TYPE]; the transformation reference also
    # describes bare TYPE. Accept only either WHOLE exact reconstruction, with
    # every finding replaced and every nonsensitive codepoint preserved.
    cursor, pieces, wrapped = 0, [], []
    for span in spans:
        pieces.extend((original[cursor : span.start], span.info_type))
        wrapped.extend((original[cursor : span.start], "[" + span.info_type + "]"))
        cursor = span.end
    pieces.append(original[cursor:])
    wrapped.append(original[cursor:])
    normalized = _canonical(value)
    if any(_canonical(original[span.start : span.end]) in normalized for span in spans):
        raise GoogleSDPFailure("RESIDUAL_VALUE", "output")
    expected_output = "".join(pieces)
    if value not in (expected_output, "".join(wrapped)):
        raise GoogleSDPFailure("OUTPUT_MISMATCH", "output")
    overview = response.overview
    total = overview.transformed_bytes
    summaries = list(overview.transformation_summaries)
    if (
        type(total) is not int
        or not 0 <= total <= MAX_INPUT_BYTES
        or len(summaries) > len(allowed_types)
    ):
        raise GoogleSDPFailure("MALFORMED_RESPONSE", "output")
    expected = Counter(span.info_type for span in spans)
    actual = Counter()
    byte_total = 0
    for summary in summaries:
        if (
            _present(summary, "field")
            or _present(summary, "record_suppress")
            or getattr(summary, "field_transformations", ())
        ):
            raise GoogleSDPFailure("MALFORMED_RESPONSE", "output")
        name = summary.info_type.name
        size = summary.transformed_bytes
        if (
            name not in expected
            or name in actual
            or type(size) is not int
            or not 0 < size <= MAX_INPUT_BYTES
        ):
            raise GoogleSDPFailure("INCOMPLETE_TRANSFORMATION", "output")
        transformation = summary.transformation
        if not _present(transformation, "replace_with_info_type_config"):
            raise GoogleSDPFailure("INCOMPLETE_TRANSFORMATION", "output")
        protobuf = getattr(transformation, "_pb", None)
        if (
            protobuf is not None
            and protobuf.WhichOneof("transformation") != "replace_with_info_type_config"
        ):
            raise GoogleSDPFailure("INCOMPLETE_TRANSFORMATION", "output")
        results = list(summary.results)
        if len(results) != 1:
            raise GoogleSDPFailure("INCOMPLETE_TRANSFORMATION", "output")
        result = results[0]
        # SUCCESS=1 in the locked proto; no warning/error detail is accepted.
        if (
            type(result.count) is not int
            or result.count <= 0
            or type(result.code) is bool
            or result.code != 1
            or result.details
        ):
            raise GoogleSDPFailure("INCOMPLETE_TRANSFORMATION", "output")
        actual[name] = result.count
        byte_total += size
    if actual != expected or byte_total != total or (bool(spans) != (total > 0)):
        raise GoogleSDPFailure("INCOMPLETE_TRANSFORMATION", "output")
    # Normalize only after exact provider output and all statistics were checked.
    return expected_output


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
            raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
        self._parent = f"projects/{project_id}/locations/{REGION}"
        if budget is not None and type(budget) is not ContentAttemptBudget:
            raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
        self._budget = budget if budget is not None else ContentAttemptBudget()
        self._operation_counts = {"inspect_attempted": 0, "deidentify_attempted": 0}
        self._test_counts = dict(self._operation_counts)
        self._real_sdk = client is None
        self._busy = threading.Lock()
        self._client = client if client is not None else _guarded(_create_client)
        if _guarded(lambda: self._client.api_endpoint == ENDPOINT) is not True:
            raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")

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
        return _guarded(lambda: self._redact(text), code="UNKNOWN", stage="sequence")

    def _redact(self, text: str) -> RedactionResult:
        started = time.monotonic()
        deadline = started + OVERALL_TIMEOUT_SECONDS
        invalid_input = _guarded(
            lambda: (
                type(text) is not str
                or not text.strip()
                or len(text.encode("utf-8")) > MAX_INPUT_BYTES
            ),
            code="INVALID_INPUT", stage="input",
        )
        if invalid_input:
            raise GoogleSDPFailure("INVALID_INPUT", "input")
        if not self._busy.acquire(blocking=False):
            raise GoogleSDPFailure("BUSY", "input")
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
            raise GoogleSDPFailure("OVERALL_TIMEOUT", "sequence")
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
        result = _rpc_guarded(
            lambda: operation(request=request, retry=None, timeout=timeout), name
        )
        if time.monotonic() - started >= timeout:
            raise GoogleSDPFailure("RPC_TIMEOUT", name)
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
        spans = _guarded(
            lambda: (
                inspection_spans(inspected, text)
                if type_map is _INFO_TYPES
                else inspection_spans(inspected, text, type_map)
            ),
            code="MALFORMED_RESPONSE", stage="inspect_response",
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
        redacted = _guarded(
            lambda: (
                _output(transformed, text, spans)
                if type_map is _INFO_TYPES
                else _output(transformed, text, spans, type_map)
            ),
            code="MALFORMED_RESPONSE", stage="output",
        )
        redacted = _guarded(
            lambda: self._normalized_output(text, spans, redacted),
            code="MALFORMED_RESPONSE", stage="normalize",
        )
        output_size = _guarded(
            lambda: len(redacted.encode("utf-8")),
            code="MALFORMED_RESPONSE", stage="normalize",
        )
        if output_size > MAX_OUTPUT_BYTES:
            raise GoogleSDPFailure("OUTPUT_LIMIT", "normalize")
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
