from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from typing import Any

from runtime.phase3.mocks import (
    MockAuthenticator,
    MockAuthorizer,
    MockPolicyEngine,
    MockTenantResolver,
    Recorder,
)
from runtime.phase3.trusted_runtime import (
    APPROVED_MODEL_ALIAS,
    SUPPORTED_ENTITIES,
    ControlFailure,
    GatewayResult,
    TrustedRuntime,
)


REQUEST_ID = "redaction-qualification-0001"
TRACE_FIELDS = {
    "schema_version",
    "request_id",
    "tenant_ref",
    "subject_ref",
    "outcome",
    "failed_stage",
    "policy_outcome",
    "redaction_status",
    "detected_categories",
    "model_alias",
    "provider_called",
    "error_category",
}


def load_cases() -> list[dict[str, Any]]:
    fixture = json.loads(
        Path("tests/phase3/presidio/synthetic-cases.json").read_text(
            encoding="utf-8"
        )
    )
    if fixture.get("schema_version") != 1:
        raise AssertionError("unsupported synthetic redaction fixture")
    cases = fixture.get("cases")
    if not isinstance(cases, list):
        raise AssertionError("malformed synthetic redaction fixture")
    return cases


def build_value(case: dict[str, Any]) -> str:
    fragments = case["fragments"]
    if case["builder"] == "join":
        return "".join(fragments)
    if case["builder"] == "email":
        return f"{fragments[0]}@{fragments[1]}.{fragments[2]}"
    if case["builder"] == "saudi_iban":
        bban = "".join(fragments)
        rearranged = bban + "SA00"
        numeric = "".join(
            str(ord(character) - 55) if character.isalpha() else character
            for character in rearranged
        )
        check_digits = 98 - (int(numeric) % 97)
        return f"SA{check_digits:02d}{bban}"
    raise AssertionError("unsupported synthetic value builder")


def request_body(message: str) -> dict[str, Any]:
    return {
        "action": "chat.complete",
        "input": {"message": message, "response_format": "json"},
    }


def span(entity: str, start: Any, end: Any, score: Any = 0.99) -> dict[str, Any]:
    return {
        "entity_type": entity,
        "start": start,
        "end": end,
        "score": score,
    }


class RedactionRecorder(Recorder):
    def __init__(self) -> None:
        super().__init__()
        self.anonymizer_calls = 0
        self.gateway_inputs: list[str] = []
        self.anonymized_hashes: list[str] = []


class ControlledAnalyzer:
    def __init__(
        self,
        recorder: RedactionRecorder,
        result: Any,
        failure: str | None = None,
    ) -> None:
        self.recorder = recorder
        self.result = result
        self.failure = failure

    def analyze(self, text: str) -> Any:
        self.recorder.sequence.append("presidio_analyzer")
        if self.failure == "timeout":
            raise TimeoutError("synthetic analyzer timeout")
        if self.failure == "unavailable":
            raise RuntimeError("synthetic analyzer unavailable")
        return self.result


class ControlledAnonymizer:
    def __init__(
        self,
        recorder: RedactionRecorder,
        result: Any | None = None,
        failure: str | None = None,
    ) -> None:
        self.recorder = recorder
        self.result = result
        self.failure = failure

    def anonymize(
        self, text: str, analyzer_results: list[dict[str, Any]]
    ) -> Any:
        self.recorder.sequence.append("presidio_anonymizer")
        self.recorder.anonymizer_calls += 1
        if self.failure == "timeout":
            raise TimeoutError("synthetic anonymizer timeout")
        if self.failure == "unavailable":
            raise RuntimeError("synthetic anonymizer unavailable")
        if self.result is not None:
            return self.result

        transformed = text
        for item in reversed(analyzer_results):
            replacement = f"[{item['entity_type']}]"
            transformed = (
                transformed[: item["start"]]
                + replacement
                + transformed[item["end"] :]
            )
        self.recorder.anonymized_hashes.append(
            hashlib.sha256(transformed.encode("utf-8")).hexdigest()
        )
        return {"text": transformed}


class RecordingGateway:
    def __init__(self, recorder: RedactionRecorder) -> None:
        self.recorder = recorder

    def complete(
        self,
        model_alias: str,
        redacted_text: str,
        metadata: dict[str, str],
    ) -> GatewayResult:
        if model_alias != APPROVED_MODEL_ALIAS:
            raise AssertionError("unapproved model alias reached gateway")
        if set(metadata) != {"correlation_id", "tenant_ref"}:
            raise AssertionError("unsafe gateway metadata")
        self.recorder.sequence.append("litellm")
        self.recorder.litellm_calls += 1
        self.recorder.gateway_inputs.append(redacted_text)
        self.recorder.sequence.append("provider")
        self.recorder.provider_calls += 1
        return GatewayResult(
            {
                "summary": "Synthetic qualification response",
                "classification": "informational",
            },
            True,
        )


class RecordingTraceSink:
    def __init__(self, recorder: RedactionRecorder) -> None:
        self.recorder = recorder

    def emit(self, envelope: dict[str, Any]) -> None:
        self.recorder.traces.append(envelope.copy())


def build_runtime(
    analyzer_result: Any,
    *,
    analyzer_failure: str | None = None,
    anonymizer_result: Any | None = None,
    anonymizer_failure: str | None = None,
) -> tuple[TrustedRuntime, RedactionRecorder]:
    recorder = RedactionRecorder()
    runtime = TrustedRuntime(
        MockAuthenticator(recorder),
        MockTenantResolver(recorder),
        MockAuthorizer(recorder),
        MockPolicyEngine(recorder),
        ControlledAnalyzer(recorder, analyzer_result, analyzer_failure),
        ControlledAnonymizer(
            recorder,
            result=anonymizer_result,
            failure=anonymizer_failure,
        ),
        RecordingGateway(recorder),
        RecordingTraceSink(recorder),
    )
    return runtime, recorder


class RedactionBoundaryTests(unittest.TestCase):
    cases = load_cases()

    def assert_sensitive_absent(self, value: str, serialized: str) -> None:
        if value in serialized:
            self.fail("sensitive fixture value escaped the redaction boundary")

    def assert_safe_trace(
        self,
        recorder: RedactionRecorder,
        sensitive_values: list[str],
        expected_categories: list[str],
    ) -> None:
        self.assertEqual(len(recorder.traces), 1)
        trace = recorder.traces[0]
        self.assertEqual(set(trace), TRACE_FIELDS)
        self.assertEqual(trace["detected_categories"], expected_categories)
        serialized = json.dumps(trace, sort_keys=True)
        for value in sensitive_values:
            self.assert_sensitive_absent(value, serialized)

    def execute_success(
        self,
        message: str,
        analysis: list[dict[str, Any]],
        sensitive_values: list[str],
    ) -> RedactionRecorder:
        runtime, recorder = build_runtime(analysis)
        runtime.execute(
            "Bearer qualification-token", request_body(message), REQUEST_ID
        )
        self.assertEqual(recorder.litellm_calls, 1)
        self.assertEqual(recorder.provider_calls, 1)
        self.assertEqual(len(recorder.gateway_inputs), 1)
        self.assertEqual(len(recorder.anonymized_hashes), 1)
        gateway_hash = hashlib.sha256(
            recorder.gateway_inputs[0].encode("utf-8")
        ).hexdigest()
        if gateway_hash != recorder.anonymized_hashes[0]:
            self.fail("gateway did not receive the anonymizer output")
        for value in sensitive_values:
            self.assert_sensitive_absent(value, recorder.gateway_inputs[0])
        expected_categories = sorted(
            {item["entity_type"] for item in analysis}
        )
        self.assert_safe_trace(recorder, sensitive_values, expected_categories)
        return recorder

    def assert_redaction_failure(
        self,
        *,
        analyzer_result: Any,
        message: str,
        sensitive_value: str,
        expected_stage: str,
        expected_category: str,
        analyzer_failure: str | None = None,
        anonymizer_result: Any | None = None,
        anonymizer_failure: str | None = None,
    ) -> None:
        runtime, recorder = build_runtime(
            analyzer_result,
            analyzer_failure=analyzer_failure,
            anonymizer_result=anonymizer_result,
            anonymizer_failure=anonymizer_failure,
        )
        with self.assertRaises(ControlFailure) as raised:
            runtime.execute(
                "Bearer qualification-token", request_body(message), REQUEST_ID
            )
        self.assertEqual(raised.exception.stage, expected_stage)
        self.assertEqual(raised.exception.category, expected_category)
        self.assertEqual(recorder.litellm_calls, 0)
        self.assertEqual(recorder.provider_calls, 0)
        if recorder.gateway_inputs:
            self.fail("gateway received input after a redaction failure")
        expected_categories = []
        if expected_stage == "presidio_anonymizer" and isinstance(
            analyzer_result, list
        ):
            expected_categories = sorted(
                {
                    item["entity_type"]
                    for item in analyzer_result
                    if isinstance(item, dict)
                    and item.get("entity_type") in SUPPORTED_ENTITIES
                }
            )
        self.assert_safe_trace(
            recorder, [sensitive_value], expected_categories
        )

    def test_fixture_covers_exactly_the_supported_entity_set(self):
        fixture_entities = {case["expected_entity"] for case in self.cases}
        self.assertEqual(fixture_entities, SUPPORTED_ENTITIES)
        self.assertEqual(len(self.cases), len(SUPPORTED_ENTITIES))

    def test_each_approved_entity_crosses_only_the_redacted_boundary(self):
        for case in self.cases:
            with self.subTest(case_id=case["case_id"]):
                value = build_value(case)
                message = f"{case['context']}: {value}"
                start = message.index(value)
                recorder = self.execute_success(
                    message,
                    [
                        span(
                            case["expected_entity"],
                            start,
                            start + len(value),
                        )
                    ],
                    [value],
                )
                if f"[{case['expected_entity']}]" not in recorder.gateway_inputs[0]:
                    self.fail("approved entity placeholder is missing")

    def test_multi_entity_request_redacts_every_value_and_reports_categories(self):
        values: list[str] = []
        message_parts: list[str] = []
        for case in self.cases:
            value = build_value(case)
            values.append(value)
            message_parts.append(f"{case['context']}: {value}")
        message = " | ".join(message_parts)
        analysis = []
        cursor = 0
        for case, value in zip(self.cases, values, strict=True):
            start = message.index(value, cursor)
            analysis.append(
                span(case["expected_entity"], start, start + len(value))
            )
            cursor = start + len(value)

        recorder = self.execute_success(message, analysis, values)
        for entity in SUPPORTED_ENTITIES:
            if f"[{entity}]" not in recorder.gateway_inputs[0]:
                self.fail("multi-entity placeholder is missing")

    def test_empty_analysis_still_passes_through_anonymizer(self):
        message = "Synthetic text containing no protected fixture value."
        runtime, recorder = build_runtime([])
        runtime.execute(
            "Bearer qualification-token", request_body(message), REQUEST_ID
        )
        self.assertEqual(recorder.anonymizer_calls, 1)
        self.assertEqual(recorder.litellm_calls, 1)
        self.assertEqual(recorder.provider_calls, 1)
        self.assertEqual(len(recorder.gateway_inputs), 1)
        self.assertEqual(
            hashlib.sha256(recorder.gateway_inputs[0].encode("utf-8")).hexdigest(),
            recorder.anonymized_hashes[0],
        )
        self.assert_safe_trace(recorder, [], [])

    def test_invalid_analyzer_results_fail_closed(self):
        sensitive_value = build_value(self.cases[0])
        message = f"Synthetic protected reference: {sensitive_value}"
        start = message.index(sensitive_value)
        valid = span(
            self.cases[0]["expected_entity"],
            start,
            start + len(sensitive_value),
        )
        invalid_results = {
            "duplicate-spans": [valid, dict(valid)],
            "overlapping-spans": [
                span("EMAIL_ADDRESS", start, start + 5),
                span("PHONE_NUMBER", start + 4, start + 9),
            ],
            "out-of-bounds-span": [
                span("EMAIL_ADDRESS", start, len(message) + 1)
            ],
            "unsupported-entity": [
                span("UNAPPROVED_ENTITY", start, start + 1)
            ],
            "extra-field": [{**valid, "original_value": "forbidden"}],
            "invalid-entity-type": [{**valid, "entity_type": 7}],
            "invalid-start-type": [{**valid, "start": True}],
            "invalid-end-type": [{**valid, "end": "invalid"}],
            "invalid-score-type": [{**valid, "score": "high"}],
            "missing-field": [
                {
                    "entity_type": valid["entity_type"],
                    "start": valid["start"],
                    "end": valid["end"],
                }
            ],
            "malformed-result": {"results": [valid]},
            "bypass-shaped-result": {
                "results": [],
                "redaction_bypass": True,
            },
        }
        for case_id, analyzer_result in invalid_results.items():
            with self.subTest(case_id=case_id):
                expected_category = (
                    "ambiguous_result"
                    if case_id == "overlapping-spans"
                    else "malformed_result"
                )
                self.assert_redaction_failure(
                    analyzer_result=analyzer_result,
                    message=message,
                    sensitive_value=sensitive_value,
                    expected_stage="presidio_analyzer",
                    expected_category=expected_category,
                )

    def test_analyzer_timeout_and_unavailability_fail_closed(self):
        sensitive_value = build_value(self.cases[0])
        message = f"Synthetic protected reference: {sensitive_value}"
        for mode, category in (("timeout", "timeout"), ("unavailable", "unavailable")):
            with self.subTest(mode=mode):
                self.assert_redaction_failure(
                    analyzer_result=[],
                    analyzer_failure=mode,
                    message=message,
                    sensitive_value=sensitive_value,
                    expected_stage="presidio_analyzer",
                    expected_category=category,
                )

    def test_invalid_anonymizer_results_fail_closed(self):
        sensitive_value = build_value(self.cases[0])
        message = f"Synthetic protected reference: {sensitive_value}"
        start = message.index(sensitive_value)
        analysis = [
            span(
                self.cases[0]["expected_entity"],
                start,
                start + len(sensitive_value),
            )
        ]
        invalid_results = {
            "malformed-result": "redacted",
            "missing-text": {"replacement": "[REDACTED]"},
            "invalid-text-type": {"text": ["REDACTED"]},
            "extra-field": {"text": "[REDACTED]", "items": []},
            "incomplete-result": {"text": message},
            "bypass-shaped-result": {
                "text": "[REDACTED]",
                "redaction_bypass": True,
            },
        }
        for case_id, anonymizer_result in invalid_results.items():
            with self.subTest(case_id=case_id):
                self.assert_redaction_failure(
                    analyzer_result=analysis,
                    anonymizer_result=anonymizer_result,
                    message=message,
                    sensitive_value=sensitive_value,
                    expected_stage="presidio_anonymizer",
                    expected_category=(
                        "incomplete_redaction"
                        if case_id == "incomplete-result"
                        else "malformed_result"
                    ),
                )

    def test_anonymizer_timeout_and_unavailability_fail_closed(self):
        sensitive_value = build_value(self.cases[0])
        message = f"Synthetic protected reference: {sensitive_value}"
        start = message.index(sensitive_value)
        analysis = [
            span(
                self.cases[0]["expected_entity"],
                start,
                start + len(sensitive_value),
            )
        ]
        for mode, category in (("timeout", "timeout"), ("unavailable", "unavailable")):
            with self.subTest(mode=mode):
                self.assert_redaction_failure(
                    analyzer_result=analysis,
                    anonymizer_failure=mode,
                    message=message,
                    sensitive_value=sensitive_value,
                    expected_stage="presidio_anonymizer",
                    expected_category=category,
                )


if __name__ == "__main__":
    unittest.main()
