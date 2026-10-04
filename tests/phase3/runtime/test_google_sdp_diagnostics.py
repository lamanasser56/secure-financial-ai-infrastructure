"""Offline SDK-envelope regressions; no provider quality or original-cause claim.

Real locked protobuf objects describe documented response shapes. The transport
is injected: no DlpServiceClient, authentication, network or SDK RPC occurs.
"""

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from runtime.phase3 import google_sdp_adapter as adapter
from runtime.phase3.sdp_context_policy import GoogleSDPContextRedactor

try:
    from google.api_core import exceptions as sdk_errors
    from google.cloud import dlp_v2
except ImportError:
    sdk_errors = dlp_v2 = None


ROOT = Path(__file__).resolve().parents[3]
# Google's published REST example, reserved example-domain synthetic data.
TEXT = "My email is test@example.com"
VALUE = "test@example.com"
TYPE = "EMAIL_ADDRESS"
PRIVATE_MARKER = "untrusted-provider-fixture-marker"


def sdk_inspection(text=TEXT, selected=None):
    selected = selected or [(text.index(VALUE), text.index(VALUE) + len(VALUE), TYPE)]
    return dlp_v2.InspectContentResponse(result={
        "findings_truncated": False,
        "findings": [
            {
                "info_type": {"name": name},
                "location": {
                    "codepoint_range": {"start": start, "end": end},
                    "byte_range": {
                        "start": len(text[:start].encode("utf-8")),
                        "end": len(text[:end].encode("utf-8")),
                    },
                },
            }
            for start, end, name in selected
        ],
    })


def sdk_output(text=TEXT, selected=None, *, bracketed=True):
    selected = selected or [(text.index(VALUE), text.index(VALUE) + len(VALUE), TYPE)]
    cursor, pieces, groups = 0, [], {}
    for start, end, name in selected:
        replacement = "[" + name + "]" if bracketed else name
        pieces.extend((text[cursor:start], replacement))
        cursor = end
        count, size = groups.get(name, (0, 0))
        groups[name] = (count + 1, size + len(text[start:end].encode("utf-8")))
    pieces.append(text[cursor:])
    return dlp_v2.DeidentifyContentResponse(
        item={"value": "".join(pieces)},
        overview={
            "transformed_bytes": sum(size for _, size in groups.values()),
            "transformation_summaries": [
                {
                    "info_type": {"name": name},
                    "transformed_bytes": size,
                    "transformation": {"replace_with_info_type_config": {}},
                    "results": [{"count": count, "code": "SUCCESS"}],
                }
                for name, (count, size) in groups.items()
            ],
        },
    )


class SDKEnvelopeTransport:
    """Injected transport whose request and response objects use the locked SDK."""

    api_endpoint = adapter.ENDPOINT

    def __init__(self, inspected, transformed, *, clock=None, delay=0):
        self.inspected, self.transformed = inspected, transformed
        self.clock, self.delay = clock, delay
        self.events = []

    def inspect_content(self, *, request, retry, timeout):
        dlp_v2.InspectContentRequest(request)  # Validate real SDK request coercion.
        self.events.append(("inspect", retry, timeout))
        if isinstance(self.inspected, Exception):
            raise self.inspected
        return self.inspected

    def deidentify_content(self, *, request, retry, timeout):
        dlp_v2.DeidentifyContentRequest(request)
        self.events.append(("deidentify", retry, timeout))
        if self.clock is not None:
            self.clock.now += self.delay
        if isinstance(self.transformed, Exception):
            raise self.transformed
        return self.transformed


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


@unittest.skipIf(dlp_v2 is None, "mandatory separate locked SDK diagnostics gate")
class GoogleSDPDiagnosticsSDKTests(unittest.TestCase):
    def assert_failure(self, operation, code, stage="output", rpc_status=None):
        with self.assertRaises(adapter.GoogleSDPFailure) as caught:
            operation()
        error = caught.exception
        expected = {"code": code, "stage": stage}
        if rpc_status is not None:
            expected["rpc_status"] = rpc_status
        self.assertEqual(error.diagnostic, expected)
        self.assertEqual(str(error), "redaction:provider_failure")
        self.assertIsNone(error.__context__)
        self.assertIsNone(error.__cause__)
        self.assertNotIn(PRIVATE_MARKER, repr(error))
        self.assertNotIn(PRIVATE_MARKER, json.dumps(error.diagnostic))
        return error

    def spans(self, text=TEXT, selected=None):
        return adapter.inspection_spans(sdk_inspection(text, selected), text)

    def guarded_output(self, response):
        return adapter._guarded(
            lambda: adapter._output(response, TEXT, self.spans()),
            code="MALFORMED_RESPONSE", stage="output",
        )

    def test_locked_sdk_fields_success_enum_and_private_presence(self):
        from importlib.metadata import version

        self.assertEqual(version("google-cloud-dlp"), "3.40.0")
        response = sdk_output()
        summary = response.overview.transformation_summaries[0]
        self.assertEqual(response.overview.transformed_bytes, 16)
        self.assertEqual(summary.transformed_bytes, 16)
        self.assertEqual(summary.results[0].count, 1)
        self.assertEqual(summary.results[0].code, 1)
        self.assertEqual(
            dlp_v2.TransformationSummary.TransformationResultCode.SUCCESS, 1
        )
        self.assertEqual(response.item._pb.WhichOneof("data_item"), "value")
        self.assertEqual(
            summary.transformation._pb.WhichOneof("transformation"),
            "replace_with_info_type_config",
        )
        self.assertFalse(summary._pb.HasField("field"))
        self.assertFalse(summary._pb.HasField("record_suppress"))

    def test_documented_bare_and_bracketed_outputs_normalize_identically(self):
        expected = "My email is EMAIL_ADDRESS"
        for bracketed in (False, True):
            with self.subTest(bracketed=bracketed):
                result = adapter._output(
                    sdk_output(bracketed=bracketed), TEXT, self.spans()
                )
                self.assertTrue(result == expected, "Exact reconstruction differs")

    def test_two_matching_findings_require_one_consistent_exact_format(self):
        text = "First test@example.com; second other@example.invalid; SAR 240.00"
        other = "other@example.invalid"
        selected = [
            (text.index(VALUE), text.index(VALUE) + len(VALUE), TYPE),
            (text.index(other), text.index(other) + len(other), TYPE),
        ]
        spans = self.spans(text, selected)
        for bracketed in (False, True):
            response = sdk_output(text, selected, bracketed=bracketed)
            actual = adapter._output(response, text, spans)
            self.assertTrue(
                actual == "First EMAIL_ADDRESS; second EMAIL_ADDRESS; SAR 240.00",
                "Nonsensitive text must remain exact",
            )
        response = sdk_output(text, selected)
        response.item.value = response.item.value.replace("[EMAIL_ADDRESS]", TYPE, 1)
        self.assert_failure(
            lambda: adapter._output(response, text, spans), "OUTPUT_MISMATCH"
        )

    def test_unicode_context_and_numeric_text_are_preserved_exactly(self):
        text = "🧪 مراجعة e\u0301: test@example.com; SAR 240.00; 2026-01-31"
        selected = [(text.index(VALUE), text.index(VALUE) + len(VALUE), TYPE)]
        actual = adapter._output(sdk_output(text, selected), text, self.spans(text))
        self.assertTrue(
            actual == "🧪 مراجعة e\u0301: EMAIL_ADDRESS; SAR 240.00; 2026-01-31",
            "Unicode context must remain exact",
        )

    def test_extra_changed_or_double_wrapped_output_is_rejected(self):
        for label, value in (
            ("extra", "My email is [EMAIL_ADDRESS] extra"),
            ("changed", "Their email is [EMAIL_ADDRESS]"),
            ("double", "My email is [[EMAIL_ADDRESS]]"),
        ):
            with self.subTest(case=label):
                response = sdk_output()
                response.item.value = value
                self.assert_failure(lambda: self.guarded_output(response), "OUTPUT_MISMATCH")

    def test_missing_item_or_wrong_oneof_is_malformed(self):
        for label, response in (
            ("absent", dlp_v2.DeidentifyContentResponse(overview=sdk_output().overview)),
            ("table", dlp_v2.DeidentifyContentResponse(
                item={"table": {"headers": [{"name": "synthetic"}]}},
                overview=sdk_output().overview,
            )),
            ("empty", dlp_v2.DeidentifyContentResponse(
                item={"value": ""}, overview=sdk_output().overview,
            )),
        ):
            with self.subTest(case=label):
                self.assert_failure(lambda: self.guarded_output(response), "MALFORMED_RESPONSE")

    def test_missing_overview_rejects_positive_transformation(self):
        response = dlp_v2.DeidentifyContentResponse(item=sdk_output().item)
        self.assert_failure(lambda: self.guarded_output(response), "INCOMPLETE_TRANSFORMATION")

    def test_output_byte_bound_is_independent_of_token_format(self):
        response = sdk_output()
        response.item.value = "ع" * 2049
        self.assert_failure(lambda: self.guarded_output(response), "OUTPUT_LIMIT")

    def test_residual_value_rejected_without_returning_text(self):
        response = sdk_output()
        response.item.value = TEXT
        self.assert_failure(lambda: self.guarded_output(response), "RESIDUAL_VALUE")

    def test_summary_count_status_bytes_and_details_fail_closed(self):
        changes = (
            ("count", lambda s: setattr(s.results[0], "count", 2)),
            ("zero-count", lambda s: setattr(s.results[0], "count", 0)),
            ("error", lambda s: setattr(s.results[0], "code", 2)),
            ("unspecified", lambda s: setattr(s.results[0], "code", 0)),
            ("unknown-status", lambda s: setattr(s.results[0], "code", 99)),
            ("bytes", lambda s: setattr(s, "transformed_bytes", 15)),
            ("zero-bytes", lambda s: setattr(s, "transformed_bytes", 0)),
            ("details", lambda s: setattr(s.results[0], "details", PRIVATE_MARKER)),
            ("missing-result", lambda s: s._pb.ClearField("results")),
            ("wrong-transform", lambda s: s._pb.ClearField("transformation")),
            ("unknown-type", lambda s: setattr(s.info_type, "name", "UNAPPROVED")),
        )
        for label, change in changes:
            with self.subTest(case=label):
                response = sdk_output()
                change(response.overview.transformation_summaries[0])
                self.assert_failure(
                    lambda: self.guarded_output(response), "INCOMPLETE_TRANSFORMATION"
                )

    def test_overview_summary_mismatch_and_excessive_bytes_fail_closed(self):
        for total, code in ((15, "INCOMPLETE_TRANSFORMATION"), (4097, "MALFORMED_RESPONSE")):
            with self.subTest(total=total):
                response = sdk_output()
                response.overview.transformed_bytes = total
                self.assert_failure(lambda: self.guarded_output(response), code)

    def test_record_or_field_transformation_is_not_text_replacement(self):
        for field in ("field", "record_suppress"):
            with self.subTest(field=field):
                response = sdk_output()
                summary = response.overview.transformation_summaries[0]
                getattr(summary._pb, field).SetInParent()
                self.assert_failure(lambda: self.guarded_output(response), "MALFORMED_RESPONSE")

    def test_sdk_rpc_statuses_are_sanitized_not_exception_messages(self):
        cases = (
            (sdk_errors.DeadlineExceeded, "RPC_TIMEOUT", "DEADLINE_EXCEEDED"),
            (sdk_errors.PermissionDenied, "RPC_STATUS", "PERMISSION_DENIED"),
            (sdk_errors.InvalidArgument, "RPC_STATUS", "INVALID_ARGUMENT"),
            (sdk_errors.ServiceUnavailable, "RPC_STATUS", "UNAVAILABLE"),
        )
        for error_type, code, status in cases:
            with self.subTest(error_type=error_type.__name__):
                transport = SDKEnvelopeTransport(
                    sdk_inspection(), error_type(PRIVATE_MARKER)
                )
                redactor = adapter.GoogleSDPRedactor("synthetic-eval", client=transport)
                self.assert_failure(
                    lambda: redactor.redact(TEXT), code, "deidentify", status
                )
                self.assertEqual([e[0] for e in transport.events], ["inspect", "deidentify"])
                self.assertTrue(all(e[1] is None for e in transport.events))
                self.assertEqual(sum(redactor.operation_counts.values()), 0)
                self.assertEqual(sum(redactor.injected_client_counts.values()), 2)

    def test_builtin_timeout_and_unknown_error_have_bounded_codes(self):
        for error, code in (
            (TimeoutError(PRIVATE_MARKER), "RPC_TIMEOUT"),
            (ValueError(PRIVATE_MARKER), "RPC_FAILURE"),
        ):
            with self.subTest(code=code):
                transport = SDKEnvelopeTransport(sdk_inspection(), error)
                redactor = adapter.GoogleSDPRedactor("synthetic-eval", client=transport)
                self.assert_failure(lambda: redactor.redact(TEXT), code, "deidentify")

    def test_local_rpc_deadline_is_rejected_after_a_returned_sdk_envelope(self):
        clock = Clock()
        transport = SDKEnvelopeTransport(
            sdk_inspection(), sdk_output(), clock=clock, delay=3
        )
        redactor = adapter.GoogleSDPRedactor("synthetic-eval", client=transport)
        with patch.object(adapter.time, "monotonic", clock):
            self.assert_failure(lambda: redactor.redact(TEXT), "RPC_TIMEOUT", "deidentify")
        self.assertEqual(len(transport.events), 2)
        self.assertTrue(all(e[1] is None and 0 < e[2] <= 3 for e in transport.events))

    def test_overall_deadline_is_distinct_and_stops_before_dispatch(self):
        transport = SDKEnvelopeTransport(sdk_inspection(), sdk_output())
        redactor = adapter.GoogleSDPRedactor("synthetic-eval", client=transport)
        with patch.object(adapter.time, "monotonic", side_effect=[100, 108]):
            self.assert_failure(lambda: redactor.redact(TEXT), "OVERALL_TIMEOUT", "sequence")
        self.assertEqual(transport.events, [])

    def test_diagnostic_values_are_finite_and_not_shared_mutable_data(self):
        error = adapter.GoogleSDPFailure(PRIVATE_MARKER, PRIVATE_MARKER, PRIVATE_MARKER)
        self.assertEqual(error.diagnostic, {"code": "UNKNOWN", "stage": "startup"})
        changed = error.diagnostic
        changed["code"] = PRIVATE_MARKER
        self.assertEqual(error.diagnostic, {"code": "UNKNOWN", "stage": "startup"})
        for code in adapter.DIAGNOSTIC_CODES:
            self.assertEqual(adapter.GoogleSDPFailure(code).diagnostic["code"], code)
        for stage in adapter.DIAGNOSTIC_STAGES:
            self.assertEqual(adapter.GoogleSDPFailure(stage=stage).diagnostic["stage"], stage)
        for status in adapter.RPC_STATUSES:
            self.assertEqual(
                adapter.GoogleSDPFailure(rpc_status=status).diagnostic["rpc_status"], status
            )

    def runner(self):
        spec = importlib.util.spec_from_file_location(
            "context_diagnostics_runner", ROOT / "scripts/evaluate-sdp-context-policy.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def first_case_transport(self, runner, *, error=None):
        case = runner.load_corpus()["cases"][0]
        selected = [
            (span["start"], span["end"], span["info_type"])
            for span in case["expected_spans"]
        ]
        response = error if error is not None else sdk_output(case["text"], selected)
        return SDKEnvelopeTransport(sdk_inspection(case["text"], selected), response)

    def test_first_case_sdk_envelopes_use_two_injected_operations_and_no_adc(self):
        runner = self.runner()
        transport = self.first_case_transport(runner)
        with patch.object(adapter, "_create_client", side_effect=AssertionError("No ADC")) as create:
            result = runner.evaluate(client=transport, first_case_only=True)
        create.assert_not_called()
        self.assertEqual(result["scope"], "context_001_diagnostic_only")
        self.assertEqual(result["sdk_attempts"], 0)
        self.assertEqual(result["injected_attempts"], 2)
        self.assertEqual(result["required_pass"], 1)
        self.assertEqual(result["required_fail"], 0)
        self.assertEqual(result["unexecuted"], 0)
        self.assertEqual([c["case_id"] for c in result["cases"]], ["context-001"])
        self.assertEqual(result["google_quality"], "unmeasured")
        self.assertFalse(result["authority_changed"])
        self.assertEqual(len(transport.events), 2)

    def test_capture_group_transformation_must_preserve_its_context_label(self):
        runner = self.runner()
        case = runner.load_corpus()["cases"][0]
        transport = self.first_case_transport(runner)
        redactor = GoogleSDPContextRedactor("synthetic-eval", client=transport)
        normalized = redactor.redact(case["text"])
        span = case["expected_spans"][0]
        expected = (case["text"][:span["start"]] + span["category"]
                    + case["text"][span["end"]:])
        self.assertTrue(normalized.text == expected, "Context label must be exact")
        transport = self.first_case_transport(runner)
        # Representative disagreement: deidentify replaced the whole regex match.
        # The capture-group contract requires the submatch, so this still blocks.
        transport.transformed.item.value = "[" + span["info_type"] + "]"
        redactor = GoogleSDPContextRedactor("synthetic-eval", client=transport)
        self.assert_failure(lambda: redactor.redact(case["text"]), "OUTPUT_MISMATCH")

    def test_final_overall_deadline_cannot_return_an_otherwise_valid_response(self):
        clock = Clock()
        transport = SDKEnvelopeTransport(sdk_inspection(), sdk_output())
        redactor = adapter.GoogleSDPRedactor("synthetic-eval", client=transport)

        def late_normalize(original, spans, validated):
            clock.now += 8
            return validated

        with patch.object(adapter.time, "monotonic", clock), patch.object(
            redactor, "_normalized_output", side_effect=late_normalize
        ):
            self.assert_failure(lambda: redactor.redact(TEXT), "OVERALL_TIMEOUT", "sequence")
        self.assertEqual(len(transport.events), 2)

    def test_first_case_rpc_diagnostic_report_does_not_contain_content(self):
        runner = self.runner()
        transport = self.first_case_transport(
            runner, error=sdk_errors.InvalidArgument(PRIVATE_MARKER)
        )
        result = runner.evaluate(client=transport, first_case_only=True)
        self.assertEqual(result["outcome"], "FAIL_CLOSED")
        self.assertEqual(result["cases"][0]["diagnostic"], {
            "code": "RPC_STATUS", "stage": "deidentify", "rpc_status": "INVALID_ARGUMENT"
        })
        encoded = json.dumps(result)
        for forbidden in (PRIVATE_MARKER, '"text"', "expected_spans", "findings", "quote"):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(result["sdk_attempts"], 0)
        self.assertEqual(result["injected_attempts"], 2)

    def test_campaign_stops_after_first_failed_case_without_retries(self):
        runner = self.runner()
        transport = self.first_case_transport(
            runner, error=sdk_errors.DeadlineExceeded(PRIVATE_MARKER)
        )
        result = runner.evaluate(client=transport)
        self.assertEqual(result["outcome"], "FAIL_CLOSED")
        self.assertEqual(result["unexecuted"], 85)
        self.assertEqual(result["required_fail"], 1)
        self.assertEqual(result["required_pass"], 0)
        self.assertEqual(len(result["cases"]), 1)
        self.assertEqual(len(transport.events), 2)
        self.assertEqual(result["injected_attempts"], 2)
        self.assertEqual(result["sdk_attempts"], 0)

    def test_live_diagnostic_requires_both_acknowledgements_before_construction(self):
        runner = self.runner()
        for environment in (
            {},
            {runner.ACK_ENV: runner.ACK_VALUE},
            {runner.DIAGNOSTIC_ACK_ENV: runner.DIAGNOSTIC_ACK_VALUE},
        ):
            with self.subTest(keys=sorted(environment)):
                with patch.dict(runner.os.environ, environment, clear=True), patch.object(
                    runner, "EvaluationRedactor", side_effect=AssertionError("No ADC")
                ) as construct:
                    with self.assertRaises(adapter.GoogleSDPFailure):
                        runner.evaluate(live=True, first_case_only=True)
                construct.assert_not_called()


if __name__ == "__main__":
    unittest.main()
