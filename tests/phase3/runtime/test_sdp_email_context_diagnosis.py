"""Locked SDK objects with injected transport; no Google detection claim or RPC."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from runtime.phase3 import google_sdp_adapter as adapter
from runtime.phase3.sdp_context_policy import GoogleSDPContextRedactor, load_policy

try:
    from google.cloud import dlp_v2
    from google.api_core import exceptions as sdk_errors
except ImportError:
    dlp_v2 = sdk_errors = None

ROOT = Path(__file__).resolve().parents[3]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


DIAGNOSTIC = module("email_diagnostic", "scripts/diagnose-sdp-email-context.py")
CAMPAIGN = module("email_campaign", "scripts/evaluate-sdp-context-policy.py")


def envelopes(text, selected):
    """Explicit selection including EMPTY; genuine SDK envelopes, no detector."""
    findings, pieces, groups, cursor = [], [], {}, 0
    for start, end, name in selected:
        findings.append({
            "info_type": {"name": name}, "likelihood": "POSSIBLE",
            "location": {"codepoint_range": {"start": start, "end": end},
                         "byte_range": {"start": len(text[:start].encode()), "end": len(text[:end].encode())}},
        })
        pieces.extend((text[cursor:start], "[" + name + "]"))
        cursor = end
        count, size = groups.get(name, (0, 0))
        groups[name] = count + 1, size + len(text[start:end].encode())
    pieces.append(text[cursor:])
    return (
        dlp_v2.InspectContentResponse(result={"findings": findings, "findings_truncated": False}),
        dlp_v2.DeidentifyContentResponse(item={"value": "".join(pieces)}, overview={
            "transformed_bytes": sum(size for _, size in groups.values()),
            "transformation_summaries": [
                {"info_type": {"name": name}, "transformed_bytes": size,
                 "transformation": {"replace_with_info_type_config": {}},
                 "results": [{"count": count, "code": "SUCCESS"}]}
                for name, (count, size) in groups.items()
            ],
        }),
    )


class Transport:
    api_endpoint = adapter.ENDPOINT

    def __init__(self, pairs):
        self.pairs, self.events = list(pairs), []

    def invoke(self, operation, request, retry, timeout):
        cls = dlp_v2.InspectContentRequest if operation == "inspect" else dlp_v2.DeidentifyContentRequest
        message = cls(request)
        self.events.append((operation, message, retry, timeout))
        response = self.pairs[0][0 if operation == "inspect" else 1]
        if operation == "deidentify":
            self.pairs.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def inspect_content(self, *, request, retry, timeout):
        return self.invoke("inspect", request, retry, timeout)

    def deidentify_content(self, *, request, retry, timeout):
        return self.invoke("deidentify", request, retry, timeout)


def score(spans, expected):
    actual = {(s.start, s.end, s.info_type) for s in spans}
    return len(actual & expected), len(actual - expected), len(expected - actual)


@unittest.skipIf(dlp_v2 is None, "requires the separate locked SDK worker gate")
class EmailContextSDKTests(unittest.TestCase):
    def test_locked_request_has_no_financial_exemption_or_threshold_override(self):
        from importlib.metadata import version
        self.assertEqual(version("google-cloud-dlp"), "3.40.0")
        _, text, expected = DIAGNOSTIC.comparisons()[0]
        transport = Transport([envelopes(text, sorted(expected))])
        result = GoogleSDPContextRedactor("synthetic-eval", client=transport).redact(text)
        self.assertEqual(result.text, "amount: EMAIL_ADDRESS")
        self.assertEqual([e[0] for e in transport.events], ["inspect", "deidentify"])
        for operation, request, retry, timeout in transport.events:
            self.assertEqual(request.item.value, text)
            self.assertEqual(request.parent, "projects/synthetic-eval/locations/us-east1")
            self.assertIsNone(retry)
            self.assertGreater(timeout, 0)
            self.assertLessEqual(timeout, 3)
            self.assertEqual(request.inspect_template_name, "")
            config = request.inspect_config
            self.assertEqual(config.min_likelihood, dlp_v2.Likelihood.POSSIBLE)
            self.assertFalse(config.include_quote)
            self.assertFalse(config.exclude_info_types)
            self.assertEqual(list(config.rule_set), [])
            self.assertEqual(list(config.min_likelihood_per_info_type), [])
            self.assertEqual([t.name for t in config.info_types], ["EMAIL_ADDRESS"])
            self.assertEqual(len(config.custom_info_types), 10)
            for custom in config.custom_info_types:
                self.assertEqual(custom.likelihood, dlp_v2.Likelihood.VERY_LIKELY)
                self.assertEqual(list(custom.detection_rules), [])
                self.assertEqual(list(custom.regex.group_indexes), [1])
            if operation == "deidentify":
                self.assertEqual(request.deidentify_template_name, "")
                types = request.deidentify_config.info_type_transformations.transformations
                self.assertEqual({t.info_types[0].name for t in types}, set(load_policy()["mapping"]))
        self.assertEqual(transport.events[0][1].inspect_config, transport.events[1][1].inspect_config)

    def test_empty_sdk_response_reproduces_metrics_without_provider_failure(self):
        _, text, expected = DIAGNOSTIC.comparisons()[0]
        transport = Transport([envelopes(text, [])])
        redactor = CAMPAIGN.EvaluationRedactor("synthetic-eval", client=transport)
        result = redactor.redact(text)
        self.assertEqual(result.text, text)
        self.assertEqual(score(redactor._evaluation_spans, expected), (0, 0, 1))
        self.assertEqual(len(transport.events), 2)
        self.assertEqual(sum(redactor.operation_counts.values()), 0)
        self.assertEqual(sum(redactor.injected_client_counts.values()), 2)

    def test_complete_email_replacements_preserve_numeric_amounts_and_unicode(self):
        value = "fixture@example.invalid"
        for text in (
            "amount: " + value + "; amount: SAR 240.00; 2026-01-31",
            "المبلغ: " + value + "؛ المجموع: ٢٤٠٫٠٠ SAR؛ 2026-01-31",
            "🧪 amount / المبلغ e\u0301: " + value + "; SAR 200.00 + 40.00",
        ):
            with self.subTest(language=text[:10]):
                start = text.index(value)
                selected = [(start, start + len(value), "EMAIL_ADDRESS")]
                redactor = GoogleSDPContextRedactor("synthetic-eval", client=Transport([envelopes(text, selected)]))
                self.assertEqual(redactor.redact(text).text, text.replace(value, "EMAIL_ADDRESS"))

    def test_numeric_only_empty_response_is_valid_and_amount_changes_are_rejected(self):
        text = DIAGNOSTIC.comparisons()[3][1]
        pair = envelopes(text, [])
        redactor = GoogleSDPContextRedactor("synthetic-eval", client=Transport([pair]))
        self.assertEqual(redactor.redact(text).text, text)
        bad = envelopes(text, [])
        bad[1].item.value = text.replace("240.00", "2400.00")
        with self.assertRaises(adapter.GoogleSDPFailure) as caught:
            GoogleSDPContextRedactor("synthetic-eval", client=Transport([bad])).redact(text)
        self.assertEqual(caught.exception.diagnostic, {"code": "OUTPUT_MISMATCH", "stage": "output"})

    def test_wrong_offset_cannot_explain_fp_zero_fn_one(self):
        _, text, expected = DIAGNOSTIC.comparisons()[0]
        start, end, name = next(iter(expected))
        spans = adapter.inspection_spans(envelopes(text, [(start + 1, end, name)])[0], text)
        self.assertEqual(score(spans, expected), (0, 1, 1))
        self.assertEqual(score([], expected), (0, 0, 1))

    def test_arabic_byte_offset_error_is_rejected_not_silently_dropped(self):
        text = "المبلغ: fixture@example.invalid"
        start = text.index("fixture")
        pair = envelopes(text, [(start, len(text), "EMAIL_ADDRESS")])
        pair[0].result.findings[0].location.byte_range.start = start
        with self.assertRaises(adapter.GoogleSDPFailure) as caught:
            GoogleSDPContextRedactor("synthetic-eval", client=Transport([pair])).redact(text)
        self.assertEqual(caught.exception.diagnostic, {"code": "MALFORMED_RESPONSE", "stage": "inspect_response"})

    def test_empty_success_resets_prior_campaign_spans(self):
        _, text, expected = DIAGNOSTIC.comparisons()[0]
        redactor = CAMPAIGN.EvaluationRedactor("synthetic-eval", client=Transport([
            envelopes(text, sorted(expected)), envelopes(text, []),
        ]))
        redactor.redact(text)
        self.assertEqual(score(redactor._evaluation_spans, expected), (1, 0, 0))
        redactor.redact(text)
        self.assertEqual(score(redactor._evaluation_spans, expected), (0, 0, 1))

    def test_nearby_custom_obfuscated_email_uses_distinct_detector(self):
        corpus = json.loads((ROOT / "evaluation/google-sdp-context/corpus.json").read_text())
        for case in corpus["cases"][56:59]:
            span, = case["expected_spans"]
            self.assertEqual(span["info_type"], "PORTFOLIO_OBFUSCATED_EMAIL")
            selected = [(span["start"], span["end"], span["info_type"])]
            redactor = CAMPAIGN.EvaluationRedactor("synthetic-eval", client=Transport([envelopes(case["text"], selected)]))
            output = redactor.redact(case["text"]).text
            self.assertEqual(output, case["text"][:span["start"]] + "EMAIL_ADDRESS" + case["text"][span["end"]:])
            self.assertEqual(score(redactor._evaluation_spans, set(selected)), (1, 0, 0))

    def test_diagnostic_mismatch_keeps_fixed_controls_separate_from_acceptance(self):
        pairs = [envelopes(text, [] if i == 0 else sorted(expected))
                 for i, (_, text, expected) in enumerate(DIAGNOSTIC.comparisons())]
        transport = Transport(pairs)
        result = DIAGNOSTIC.evaluate(client=transport)
        self.assertEqual(result["outcome"], "OFFLINE_GOOGLE_UNPROVEN")
        self.assertEqual(result["injected_attempts"], 8)
        self.assertEqual(result["sdk_attempts"], 0)
        self.assertEqual(result["observations"][0]["fn"], 1)
        self.assertEqual(result["observations"][1]["returned_likelihood_counts"], {"POSSIBLE": 1})
        self.assertEqual(len(transport.events), 8)
        self.assertEqual(result["unexecuted"], 0)

    def test_diagnostic_rpc_failure_stops_and_suppresses_exception(self):
        pairs = [envelopes(text, sorted(expected)) for _, text, expected in DIAGNOSTIC.comparisons()]
        pairs[0] = (pairs[0][0], sdk_errors.ServiceUnavailable("private-provider-text"))
        transport = Transport(pairs)
        result = DIAGNOSTIC.evaluate(client=transport)
        self.assertEqual(result["outcome"], "FAIL_CLOSED")
        self.assertEqual(result["injected_attempts"], 2)
        self.assertEqual(result["unexecuted"], 3)
        self.assertEqual(result["observations"][0]["diagnostic"], {
            "code": "RPC_STATUS", "stage": "deidentify", "rpc_status": "UNAVAILABLE",
        })
        self.assertNotIn("private-provider-text", json.dumps(result))

    def test_shared_budget_prevents_ninth_attempt_and_timeout_keeps_limits(self):
        _, text, expected = DIAGNOSTIC.comparisons()[0]
        transport = Transport([envelopes(text, sorted(expected)) for _ in range(5)])
        redactor = GoogleSDPContextRedactor("synthetic-eval", client=transport, budget=adapter.ContentAttemptBudget(8))
        for _ in range(4):
            redactor.redact(text)
        with self.assertRaises(adapter.GoogleSDPFailure) as caught:
            redactor.redact(text)
        self.assertEqual(caught.exception.diagnostic["code"], "BUDGET_EXHAUSTED")
        self.assertEqual(len(transport.events), 8)
        pair = envelopes(text, sorted(expected))
        pair = (pair[0], sdk_errors.DeadlineExceeded("private-timeout"))
        result = DIAGNOSTIC.evaluate(client=Transport([pair]))
        self.assertEqual(result["observations"][0]["diagnostic"]["code"], "RPC_TIMEOUT")

    def test_invalid_likelihood_and_oversized_output_stop_with_finite_codes(self):
        _, text, expected = DIAGNOSTIC.comparisons()[0]
        pair = envelopes(text, sorted(expected))
        pair[0].result.findings[0].likelihood = 99
        value = DIAGNOSTIC.evaluate(client=Transport([pair]))
        self.assertEqual(value["injected_attempts"], 1)
        self.assertEqual(value["observations"][0]["diagnostic"], {"code": "MALFORMED_RESPONSE", "stage": "inspect_response"})
        pair = envelopes(text, sorted(expected))
        pair[1].item.value = "x" * 4097
        value = DIAGNOSTIC.evaluate(client=Transport([pair]))
        self.assertEqual(value["injected_attempts"], 2)
        self.assertEqual(value["observations"][0]["diagnostic"], {"code": "OUTPUT_LIMIT", "stage": "output"})

    def test_successful_injected_results_cannot_underreport_attempts(self):
        pairs = [envelopes(text, sorted(expected)) for _, text, expected in DIAGNOSTIC.comparisons()]
        value = DIAGNOSTIC.evaluate(client=Transport(pairs))
        value["injected_attempts"] = 7
        with self.assertRaises(ValueError):
            DIAGNOSTIC.validate_result(value)


class EmailDiagnosticAdmissionTests(unittest.TestCase):
    def test_live_acknowledgements_precede_client_construction(self):
        for missing in DIAGNOSTIC.ACKS:
            environment = {k: v for k, v in DIAGNOSTIC.ACKS.items() if k != missing}
            with patch.dict("os.environ", environment, clear=True), patch.object(adapter, "_create_client") as client:
                with self.assertRaises(adapter.GoogleSDPFailure):
                    DIAGNOSTIC.evaluate(True)
                client.assert_not_called()
        with self.assertRaises(adapter.GoogleSDPFailure):
            DIAGNOSTIC.evaluate(True, client=object())

    def test_reference_has_no_client_or_provider_and_bounds_output(self):
        with patch.object(adapter, "_create_client") as client:
            value = DIAGNOSTIC.evaluate()
        client.assert_not_called()
        self.assertEqual(value["sdk_attempts"], 0)
        self.assertEqual(value["injected_attempts"], 0)
        self.assertEqual(value["mode"], "offline_reference")
        self.assertLess(len(json.dumps(value).encode()), 4096)
        self.assertEqual(DIAGNOSTIC.read_result(json.dumps(value).encode()), value)

    def test_sequence_deadline_runs_no_extra_case(self):
        times = iter((100, 100, 161))
        value = DIAGNOSTIC.evaluate(clock=lambda: next(times))
        self.assertEqual(value["unexecuted"], 3)
        self.assertEqual(value["sequence_diagnostic"], {"code": "OVERALL_TIMEOUT", "stage": "sequence"})
        self.assertEqual(value["outcome"], "FAIL_CLOSED")

    def test_raw_fields_bad_counts_and_invalid_minimized_results_are_denied(self):
        valid = DIAGNOSTIC.evaluate()
        for key, item in (("raw_text", "private"), ("sdk_attempts", 1), ("metadata_sdk_attempts", 1),
                          ("scope", "context_pattern_v1_campaign"), ("schema_version", True),
                          ("outcome", "PASS"), ("unexecuted", 1)):
            with self.subTest(field=key):
                bad = copy.deepcopy(valid)
                bad[key] = item
                with self.assertRaises(ValueError):
                    DIAGNOSTIC.validate_result(bad)
        for payload in (b"x" * 4097, b"\xff", b'{"scope":1,"scope":2}'):
            with self.assertRaises((ValueError, UnicodeError)):
                DIAGNOSTIC.read_result(payload)

    def test_arbitrary_input_selectors_are_rejected_before_program_admission(self):
        for args in (("--text", "private"), ("--case", "context-061"), ("--corpus", "/tmp/x"),
                     ("--endpoint", "https://unapproved.invalid"), ("--diagnostic-first-case",), ("--campaign",)):
            result = subprocess.run([sys.executable, str(ROOT / "scripts/diagnose-sdp-email-context.py"), *args], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(b"private", result.stdout + result.stderr)
            self.assertNotIn(b"unapproved.invalid", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
