"""Offline safety/deadline tests; injected clients are never provider evidence."""

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from runtime.phase3 import google_sdp_adapter as adapter
from runtime.phase3.mocks import build_mock_runtime
from test_google_sdp_adapter import (
    FakeClient,
    PROJECT,
    TEXT,
    finding,
    inspection,
    output,
)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, amount):
        self.now += amount


class RobustnessTests(unittest.TestCase):
    def blocked(self, client, text=TEXT, budget=None):
        redactor = adapter.GoogleSDPRedactor(PROJECT, client=client, budget=budget)
        with self.assertRaises(adapter.GoogleSDPFailure) as error:
            redactor.redact(text)
        self.assertEqual(str(error.exception), "redaction:provider_failure")
        self.assertIsNone(error.exception.__context__)
        self.assertIsNone(error.exception.__cause__)
        self.assertEqual(sum(redactor.operation_counts.values()), 0)
        return redactor

    def test_truncated_missing_or_nonboolean_completeness_blocks_second_call(self):
        for response in (
            inspection([finding()], True),
            inspection([], 0),
            inspection([], None),
            SimpleNamespace(result=SimpleNamespace(findings=[])),
        ):
            with self.subTest(response_type=type(response).__name__):
                client = FakeClient(inspect=response)
                self.blocked(client)
                self.assertEqual([event[0] for event in client.events], ["inspect"])

    def test_unicode_codepoints_and_utf8_bytes_agree(self):
        text = "🧪 مراجعة e\u0301 fixture@example.invalid; SAR 240.00"
        span = finding(text)
        start, end = (
            span.location.codepoint_range.start,
            span.location.codepoint_range.end,
        )
        span.location.byte_range = SimpleNamespace(
            start=len(text[:start].encode()), end=len(text[:end].encode())
        )
        expected = text[:start] + "EMAIL_ADDRESS" + text[end:]
        client = FakeClient(
            inspect=inspection([span]), deidentify=output(expected, [span], text)
        )
        result = adapter.GoogleSDPRedactor(PROJECT, client=client).redact(text)
        self.assertEqual(result.text, expected)
        span.location.byte_range.start = start  # Unicode offset is not a byte offset.
        self.blocked(FakeClient(inspect=inspection([span])), text)

    def test_zero_start_is_valid_but_missing_and_boolean_offsets_are_not(self):
        text = "fixture@example.invalid"
        span = finding(text)
        result = adapter.GoogleSDPRedactor(
            PROJECT,
            client=FakeClient(
                inspect=inspection([span]),
                deidentify=output("EMAIL_ADDRESS", [span], text),
            ),
        ).redact(text)
        self.assertEqual(result.text, "EMAIL_ADDRESS")
        for start, end in (
            (True, len(text)),
            (0, False),
            (-1, len(text)),
            (0, 0),
            (0, len(text) + 1),
        ):
            invalid = deepcopy(span)
            (
                invalid.location.codepoint_range.start,
                invalid.location.codepoint_range.end,
            ) = (start, end)
            self.blocked(FakeClient(inspect=inspection([invalid])), text)
        del span.location.codepoint_range
        self.blocked(FakeClient(inspect=inspection([span])), text)

    def test_duplicates_conflicting_overlaps_quotes_and_nested_locations_rejected(self):
        first = finding()
        conflicting = deepcopy(first)
        conflicting.info_type.name = "PHONE_NUMBER"
        quote = deepcopy(first)
        quote.quote = "fixture@example.invalid"
        nested = deepcopy(first)
        nested.location.content_locations = [object()]
        for values in (
            [first, first],
            [first, conflicting],
            [quote],
            [nested],
            [first] * 1001,
        ):
            self.blocked(FakeClient(inspect=inspection(values)))

    def test_nonempty_partial_extra_encoded_and_wrong_transformation_outputs_rejected(
        self,
    ):
        for value in (
            TEXT,
            "Contact EMAIL_ADDRESS extra",
            "EMAIL_ADDRESS",
            "Contact [EMAIL_ADDRESS]",
            "Contact Zml4dHVyZUBleGFtcGxlLmludmFsaWQ=",
            "x" * 4097,
        ):
            self.blocked(FakeClient(deidentify=output(value, [finding()])))

    def test_all_allowed_text_preserved_not_just_sensitive_fragment_removed(self):
        text = "Contact fixture@example.invalid; SAR 240.00; 2026-01; 0123456789abcdef"
        span = finding(text)
        expected = text.replace("fixture@example.invalid", "EMAIL_ADDRESS")
        client = FakeClient(
            inspect=inspection([span]), deidentify=output(expected, [span], text)
        )
        self.assertEqual(
            adapter.GoogleSDPRedactor(PROJECT, client=client).redact(text).text,
            expected,
        )
        self.blocked(
            FakeClient(
                inspect=inspection([span]),
                deidentify=output(expected.replace("240.00", "0.00"), [span], text),
            ),
            text,
        )

    def test_response_statistics_cannot_hide_failed_or_missing_transforms(self):
        good = output("Contact EMAIL_ADDRESS", [finding()])
        broken = []
        for key, value in (
            ("code", 2),
            ("code", 0),
            ("code", True),
            ("count", 0),
            ("count", 2),
            ("count", True),
            ("details", "private-warning"),
        ):
            response = deepcopy(good)
            setattr(
                response.overview.transformation_summaries[0].results[0], key, value
            )
            broken.append(response)
        missing = deepcopy(good)
        missing.overview.transformation_summaries = []
        broken.append(missing)
        for value in (-1, 0, True, 4097):
            response = deepcopy(good)
            response.overview.transformed_bytes = value
            broken.append(response)
        duplicate = deepcopy(good)
        duplicate.overview.transformation_summaries *= 2
        broken.append(duplicate)
        wrong = deepcopy(good)
        wrong.overview.transformation_summaries[0].transformation = SimpleNamespace()
        broken.append(wrong)
        for field in ("field", "record_suppress", "field_transformations"):
            ambiguous = deepcopy(good)
            setattr(ambiguous.overview.transformation_summaries[0], field, [object()])
            broken.append(ambiguous)
        for response in broken:
            self.blocked(FakeClient(deidentify=response))

    def test_exact_byte_limit_and_invalid_unicode_make_no_sdk_calls(self):
        text = "ع" * 2048
        client = FakeClient(inspect=inspection(), deidentify=output(text))
        redactor = adapter.GoogleSDPRedactor(PROJECT, client=client)
        self.assertEqual(redactor.redact(text).text, text)
        before = len(client.events)
        for invalid in (text + "ع", "\ud800", "x" * 4097):
            with self.assertRaises(adapter.GoogleSDPFailure):
                redactor.redact(invalid)
        self.assertEqual(len(client.events), before)
        self.assertEqual(sum(redactor.operation_counts.values()), 0)

    def test_shared_budget_survives_new_candidate_and_accounts_failure_once(self):
        budget = adapter.ContentAttemptBudget(2)
        first = adapter.GoogleSDPRedactor(
            PROJECT, client=FakeClient(inspect=TimeoutError("private")), budget=budget
        )
        with self.assertRaises(adapter.GoogleSDPFailure):
            first.redact(TEXT)
        self.assertEqual(budget.used, 1)
        second = FakeClient()
        self.blocked(second, budget=budget)
        self.assertEqual(second.events, [])
        self.assertEqual(budget.used, 1)
        for limit in (True, 0, 175, -1, "18"):
            with self.assertRaises(adapter.GoogleSDPFailure):
                adapter.ContentAttemptBudget(limit)

    def test_default_seed_ceiling_exhausts_exactly_after_nine_pairs(self):
        client = FakeClient()
        redactor = adapter.GoogleSDPRedactor(PROJECT, client=client)
        for _ in range(9):
            redactor.redact(TEXT)
        with self.assertRaises(adapter.GoogleSDPFailure):
            redactor.redact(TEXT)
        self.assertEqual(
            redactor.injected_client_counts,
            {"inspect_attempted": 9, "deidentify_attempted": 9},
        )
        self.assertEqual(sum(redactor.operation_counts.values()), 0)
        self.assertEqual(len(client.events), 18)

    def test_second_rpc_uses_remaining_monotonic_budget(self):
        clock, timeouts = Clock(), []
        client = FakeClient()
        real = adapter.inspection_spans

        def inspect(**kwargs):
            timeouts.append(kwargs["timeout"])
            clock.advance(0.5)
            return inspection([finding()])

        def parse(response, text):
            result = real(response, text)
            clock.advance(7)
            return result

        def deidentify(**kwargs):
            timeouts.append(kwargs["timeout"])
            clock.advance(0.1)
            return output("Contact EMAIL_ADDRESS", [finding()])

        client.inspect_content, client.deidentify_content = inspect, deidentify
        with patch.object(adapter.time, "monotonic", clock), patch.object(
            adapter, "inspection_spans", parse
        ):
            adapter.GoogleSDPRedactor(PROJECT, client=client).redact(TEXT)
        self.assertEqual(timeouts, [3, 0.5])

    def test_expired_overall_or_rpc_deadline_prevents_next_operation(self):
        for during_parse in (False, True):
            clock, client = Clock(), FakeClient()
            real_inspect, real_parse = client.inspect_content, adapter.inspection_spans

            def inspect(**kwargs):
                clock.advance(0.5 if during_parse else 3)
                return real_inspect(**kwargs)

            def parse(response, text):
                clock.advance(8)
                return real_parse(response, text)

            client.inspect_content = inspect
            with patch.object(adapter.time, "monotonic", clock), patch.object(
                adapter, "inspection_spans", parse
            ):
                self.blocked(client)
            self.assertEqual([event[0] for event in client.events], ["inspect"])

    def test_failed_second_call_and_late_validation_never_return_success(self):
        self.blocked(FakeClient(deidentify=PermissionError("private-provider-detail")))
        clock, real = Clock(), adapter._output

        def late(*args):
            result = real(*args)
            clock.advance(8)
            return result

        with patch.object(adapter.time, "monotonic", clock), patch.object(
            adapter, "_output", late
        ):
            self.blocked(FakeClient())

    def test_client_construction_is_not_dispatch_and_attempt_counters_keep_failed_sdk_calls(
        self,
    ):
        client = FakeClient(inspect=PermissionError("private"))
        with patch.object(adapter, "_create_client", return_value=client):
            redactor = adapter.GoogleSDPRedactor(PROJECT)
        self.assertEqual(sum(redactor.operation_counts.values()), 0)
        with self.assertRaises(adapter.GoogleSDPFailure):
            redactor.redact(TEXT)
        # Factory mocked here: this proves accounting code, not a real provider call.
        self.assertEqual(
            redactor.operation_counts,
            {"inspect_attempted": 1, "deidentify_attempted": 0},
        )
        self.assertEqual(sum(redactor.injected_client_counts.values()), 0)

    def test_redaction_failure_contained_before_external_model_boundary(self):
        runtime, recorder = build_mock_runtime()
        runtime.redactor = adapter.GoogleSDPRedactor(
            PROJECT, client=FakeClient(inspect=inspection([], True))
        )
        with self.assertRaises(Exception):
            runtime.execute(
                "Bearer qualification-token",
                {
                    "action": "chat.complete",
                    "input": {
                        "message": "Synthetic input only.",
                        "response_format": "json",
                    },
                },
                "qualification-sdp-failure",
            )
        self.assertEqual((recorder.litellm_calls, recorder.provider_calls), (0, 0))
        self.assertNotIn("Synthetic input only.", str(recorder.traces))


try:
    from google.cloud import dlp_v2
except ImportError:
    dlp_v2 = None


@unittest.skipIf(dlp_v2 is None, "optional SDK; mandatory separate worker SDK gate")
class LockedSDKShapeTests(unittest.TestCase):
    def test_real_proto_presence_oneofs_unicode_and_summary_enums(self):
        from importlib.metadata import version

        self.assertEqual(version("google-cloud-dlp"), "3.40.0")
        text = "🧪 رسالة fixture@example.invalid"
        start = text.index("fixture")
        response = dlp_v2.InspectContentResponse(
            result={
                "findings": [
                    {
                        "info_type": {"name": "EMAIL_ADDRESS"},
                        "location": {
                            "codepoint_range": {"start": start, "end": len(text)},
                            "byte_range": {
                                "start": len(text[:start].encode()),
                                "end": len(text.encode()),
                            },
                        },
                    }
                ]
            }
        )
        spans = adapter.inspection_spans(response, text)
        size = len(text[start:].encode())
        transformed = dlp_v2.DeidentifyContentResponse(
            item={"value": text[:start] + "EMAIL_ADDRESS"},
            overview={
                "transformed_bytes": size,
                "transformation_summaries": [
                    {
                        "info_type": {"name": "EMAIL_ADDRESS"},
                        "transformed_bytes": size,
                        "transformation": {"replace_with_info_type_config": {}},
                        "results": [{"count": 1, "code": 1}],
                    }
                ],
            },
        )
        self.assertEqual(
            adapter._output(transformed, text, spans), text[:start] + "EMAIL_ADDRESS"
        )
        response.result.findings_truncated = True
        with self.assertRaises(ValueError):
            adapter.inspection_spans(response, text)
        with self.assertRaises(ValueError):
            adapter.inspection_spans(dlp_v2.InspectContentResponse(), text)
        transformed.item = dlp_v2.ContentItem(
            table={"headers": [{"name": "unsupported"}]}
        )
        with self.assertRaises(ValueError):
            adapter._output(transformed, text, spans)


if __name__ == "__main__":
    unittest.main()
