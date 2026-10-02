"""Offline, synthetic-only tests for the SDP evaluation harness."""

import base64
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import urllib.request

from jsonschema import Draft202012Validator, ValidationError
from runtime.phase3.trusted_runtime import RedactionResult


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "google_sdp_evaluation", ROOT / "scripts/evaluate-google-sdp.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class FakeRedactor:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def redact(self, text):
        self.calls.append(text)
        if text in self.responses:
            response = self.responses[text]
            if isinstance(response, Exception):
                raise response
            return response
        if "@example." in text:
            return RedactionResult("[REDACTED]", ("EMAIL_ADDRESS",))
        return RedactionResult(text, ())


class GoogleSDPEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.corpus = runner.load_corpus()
        self.fake = FakeRedactor()

    def run_fake(self, corpus=None, fake=None):
        with patch.dict(os.environ, {runner.ACK_ENV: runner.ACK_VALUE}):
            with patch.object(runner, "_live_redactor", side_effect=AssertionError("real client")):
                return runner.evaluate(corpus or self.corpus, live=True, redactor=fake or self.fake)

    def assert_corpus_failure(self, corpus):
        with self.assertRaises(runner.EvaluationFailure) as raised:
            runner.validate_corpus(corpus)
        self.assertEqual(str(raised.exception), "evaluation:invalid_corpus")

    def test_committed_corpus_is_valid_and_machine_labelled(self):
        self.assertEqual(runner.validate_corpus(self.corpus), self.corpus)
        self.assertTrue(all(case["synthetic"] is True for case in self.corpus["cases"].values()))
        counts = {name: sum(case["expected"]["expectation"] == name
                            for case in self.corpus["cases"].values())
                  for name in ("must_detect", "must_not_detect", "observation_only")}
        self.assertEqual(counts, {"must_detect": 4, "must_not_detect": 2, "observation_only": 3})
        self.assertIn("SAUDI_NATIONAL_ID", self.corpus["deferred_unproven"])
        self.assertIn("ARABIC_OCR", self.corpus["deferred_unproven"])

    def test_unknown_corpus_fields_are_rejected(self):
        corpus = deepcopy(self.corpus)
        corpus["arbitrary"] = "forbidden"
        self.assert_corpus_failure(corpus)
        corpus = deepcopy(self.corpus)
        corpus["cases"]["email-basic-001"]["input"]["arbitrary"] = "forbidden"
        self.assert_corpus_failure(corpus)

    def test_duplicate_case_ids_are_rejected_before_validation(self):
        raw = json.dumps(self.corpus)
        key = '"email-basic-001": '
        duplicate = key + json.dumps(self.corpus["cases"]["email-basic-001"]) + ", " + key
        raw = raw.replace(key, duplicate, 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            path.write_text(raw, encoding="utf-8")
            with self.assertRaises(runner.EvaluationFailure) as raised:
                runner.load_corpus(path)
        self.assertEqual(str(raised.exception), "evaluation:invalid_corpus")

    def test_invalid_or_missing_expectations_are_rejected(self):
        for expected in (
            {"expectation": "maybe", "categories": []},
            {"expectation": "must_detect", "categories": []},
            {"expectation": "must_not_detect", "categories": ["EMAIL_ADDRESS"]},
            {"expectation": "must_detect"},
        ):
            corpus = deepcopy(self.corpus)
            corpus["cases"]["email-basic-001"]["expected"] = expected
            self.assert_corpus_failure(corpus)

    def test_provider_selection_and_configuration_fields_are_rejected(self):
        for location in ("root", "case", "input", "expected"):
            for field in ("endpoint", "region", "project", "credentials", "provider", "model"):
                corpus = deepcopy(self.corpus)
                target = {
                    "root": corpus,
                    "case": corpus["cases"]["email-basic-001"],
                    "input": corpus["cases"]["email-basic-001"]["input"],
                    "expected": corpus["cases"]["email-basic-001"]["expected"],
                }[location]
                target[field] = "untrusted"
                with self.subTest(location=location, field=field):
                    self.assert_corpus_failure(corpus)

    def test_default_mode_validates_and_makes_zero_provider_calls(self):
        with patch.dict(os.environ, {runner.ACK_ENV: ""}):
            with patch.object(runner, "_live_redactor", side_effect=AssertionError("real client")):
                report = runner.evaluate(redactor=self.fake)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(report["run_mode"], "offline")
        self.assertEqual(report["aggregate"]["status_counts"],
                         {"pass": 0, "fail": 0, "inconclusive": 9})
        self.assertEqual(report["outcome"], runner.OUTCOME_INCONCLUSIVE)
        self.assertTrue(all(case["failure_code"] == "not_executed" for case in report["cases"]))

    def test_each_live_control_alone_makes_zero_provider_calls(self):
        with patch.dict(os.environ, {runner.ACK_ENV: ""}):
            with self.assertRaises(runner.EvaluationFailure) as raised:
                runner.evaluate(self.corpus, live=True, redactor=self.fake)
        self.assertEqual(str(raised.exception), "evaluation:authorization_required")
        with patch.dict(os.environ, {runner.ACK_ENV: runner.ACK_VALUE}):
            report = runner.evaluate(self.corpus, redactor=self.fake)
        self.assertEqual(report["run_mode"], "offline")
        self.assertEqual(self.fake.calls, [])

    def test_both_controls_use_only_the_injected_fake(self):
        report = self.run_fake()
        self.assertEqual(len(self.fake.calls), len(self.corpus["cases"]))
        self.assertEqual(report["run_mode"], "live")
        self.assertEqual(report["aggregate"]["status_counts"],
                         {"pass": 6, "fail": 0, "inconclusive": 3})
        self.assertEqual(report["outcome"], runner.OUTCOME_INCONCLUSIVE)
        self.assertEqual(report["provider_operations"]["accounting"], "test_double_unavailable")
        self.assertIsNone(report["provider_operations"]["inspect_attempted"])

    def test_changed_live_corpus_is_rejected_before_provider_construction(self):
        changed = deepcopy(self.corpus)
        changed["cases"]["email-basic-001"]["input"]["text"] = "Changed synthetic text."
        with patch.dict(os.environ, {runner.ACK_ENV: runner.ACK_VALUE}):
            with patch.object(runner, "_live_redactor", side_effect=AssertionError("real client")) as construct:
                with self.assertRaises(runner.EvaluationFailure):
                    runner.evaluate(changed, live=True, redactor=self.fake)
                construct.assert_not_called()
        self.assertEqual(self.fake.calls, [])

    def test_real_adapter_reports_bounded_sdk_attempts_with_fake_transport(self):
        class Client:
            api_endpoint = runner.ENDPOINT

            def inspect_content(self, *, request, retry, timeout):
                self.check(retry, timeout)
                return SimpleNamespace(result=SimpleNamespace(findings=[]))

            def deidentify_content(self, *, request, retry, timeout):
                self.check(retry, timeout)
                return SimpleNamespace(item=SimpleNamespace(value=request["item"]["value"]))

            def check(self, retry, timeout):
                if retry is not None or timeout != 20:
                    raise AssertionError("unbounded operation")

        redactor = runner.GoogleSDPRedactor("synthetic-eval", client=Client())
        report = self.run_fake(fake=redactor)
        self.assertEqual(report["provider_operations"], {
            "accounting": "sdk_invocation_attempts", "inspect_attempted": 9,
            "deidentify_attempted": 9, "application_retries": 0, "rpc_timeout_seconds": 20,
        })
        self.assertNotIn("fixture@example.com", json.dumps(report))

    def test_explicit_client_construction_keeps_fixed_region_and_endpoint(self):
        with patch.dict(os.environ, {runner.PROJECT_ENV: "synthetic-eval"}):
            with patch.object(runner, "GoogleSDPRedactor", return_value=self.fake) as construct:
                self.assertIs(runner._live_redactor(), self.fake)
        construct.assert_called_once_with(
            "synthetic-eval", endpoint=runner.ENDPOINT, region=runner.REGION)

    def test_required_detection_and_negative_controls_are_classified(self):
        report = self.run_fake()
        cases = {case["case_id"]: case for case in report["cases"]}
        self.assertEqual(cases["email-basic-001"]["status"], "pass")
        self.assertEqual(cases["email-basic-001"]["observed_categories"], ["EMAIL_ADDRESS"])
        self.assertEqual(cases["control-plain-005"]["status"], "pass")
        self.assertEqual(cases["control-plain-005"]["observed_categories"], [])

    def test_observation_only_cannot_create_authoritative_pass(self):
        report = self.run_fake()
        self.assertTrue(all(case["status"] == "inconclusive" for case in report["cases"]
                            if case["case_id"].startswith("observe-")))
        self.assertNotEqual(report["outcome"], "PASS FOR FURTHER BOUNDED INTEGRATION")

    def test_missing_required_detection_fails_closed(self):
        text = self.corpus["cases"]["email-basic-001"]["input"]["text"]
        fake = FakeRedactor({text: RedactionResult(text, ())})
        report = self.run_fake(fake=fake)
        case = next(case for case in report["cases"] if case["case_id"] == "email-basic-001")
        self.assertEqual((case["status"], case["failure_code"]), ("fail", "missing_expected"))
        self.assertEqual(report["outcome"], runner.OUTCOME_FAIL)

    def test_unexpected_negative_detection_fails_closed(self):
        text = self.corpus["cases"]["control-plain-005"]["input"]["text"]
        fake = FakeRedactor({text: RedactionResult("[REDACTED]", ("EMAIL_ADDRESS",))})
        report = self.run_fake(fake=fake)
        case = next(case for case in report["cases"] if case["case_id"] == "control-plain-005")
        self.assertEqual((case["status"], case["failure_code"]), ("fail", "unexpected_detection"))
        self.assertEqual(report["outcome"], runner.OUTCOME_FAIL)

    def test_provider_failure_never_exposes_raw_marker(self):
        text = self.corpus["cases"]["email-basic-001"]["input"]["text"]
        fake = FakeRedactor({text: RuntimeError("raw-provider-marker fixture@example.com")})
        report = self.run_fake(fake=fake)
        serialized = json.dumps(report)
        self.assertNotIn("raw-provider-marker", serialized)
        self.assertNotIn("fixture@example.com", serialized)
        case = next(case for case in report["cases"] if case["case_id"] == "email-basic-001")
        self.assertEqual((case["status"], case["failure_code"]), ("fail", "provider_failure"))

    def test_malformed_provider_result_fails_closed(self):
        text = self.corpus["cases"]["email-basic-001"]["input"]["text"]
        for result in (
            None,
            {"text": "raw-provider-marker", "categories": ["EMAIL_ADDRESS"]},
            RedactionResult("raw-provider-marker", ("UNKNOWN",)),
            RedactionResult(text, ("EMAIL_ADDRESS",)),
        ):
            fake = FakeRedactor({text: result})
            report = self.run_fake(fake=fake)
            case = next(case for case in report["cases"] if case["case_id"] == "email-basic-001")
            self.assertEqual((case["status"], case["failure_code"]), ("fail", "malformed_result"))
            self.assertNotIn("raw-provider-marker", json.dumps(report))

    def test_result_schema_rejects_raw_fields_and_blocks_artifact(self):
        report = runner.evaluate(self.corpus)
        invalid = deepcopy(report)
        invalid["raw_text"] = "raw-provider-marker"
        schema = runner._schema(runner.RESULT_SCHEMA_PATH)
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(invalid)
        original_schema = runner._schema
        strict_schema = deepcopy(schema)
        strict_schema["required"].append("missing_required_field")
        with patch.object(runner, "_schema", side_effect=lambda path: (
            strict_schema if path == runner.RESULT_SCHEMA_PATH else original_schema(path)
        )):
            with self.assertRaises(runner.EvaluationFailure) as raised:
                runner.evaluate(self.corpus)
        self.assertEqual(str(raised.exception), "evaluation:invalid_artifact")

    def test_sanitizer_rejects_a_fixture_that_would_be_echoed_as_case_id(self):
        corpus = deepcopy(self.corpus)
        case = corpus["cases"].pop("email-basic-001")
        case["input"]["text"] = "email-sample-basic-001"
        corpus["cases"]["email-sample-basic-001"] = case
        with self.assertRaises(runner.EvaluationFailure) as raised:
            runner.evaluate(corpus)
        self.assertEqual(str(raised.exception), "evaluation:invalid_artifact")

    def test_result_contains_no_raw_encoded_or_hashed_fixture(self):
        report = self.run_fake()
        rendered = json.dumps(report, sort_keys=True)
        for case in self.corpus["cases"].values():
            text = case["input"]["text"]
            self.assertNotIn(text, rendered)
            self.assertNotIn(base64.b64encode(text.encode()).decode(), rendered)
            self.assertNotIn(text.encode().hex(), rendered)
            self.assertNotIn(hashlib.sha256(text.encode()).hexdigest(), rendered)
        self.assertEqual(set(report), {"run_mode", "provider_operations", "cases", "aggregate", "outcome"})

    def test_cli_default_emits_only_sanitized_offline_result(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {runner.ACK_ENV: ""}):
            with redirect_stdout(output), redirect_stderr(errors):
                status = runner.main([])
        self.assertEqual(status, 0)
        self.assertEqual(errors.getvalue(), "")
        report = json.loads(output.getvalue())
        self.assertEqual(report["run_mode"], "offline")
        self.assertNotIn("fixture@example.com", output.getvalue())

    def test_no_external_network_or_litellm_call(self):
        with patch.dict(os.environ, {runner.ACK_ENV: runner.ACK_VALUE}):
            with patch.object(socket.socket, "connect", side_effect=AssertionError("network")):
                with patch.object(urllib.request, "urlopen", side_effect=AssertionError("network")):
                    report = runner.evaluate(self.corpus, live=True, redactor=self.fake)
        self.assertEqual(report["aggregate"]["status_counts"]["fail"], 0)
        self.assertEqual(len(self.fake.calls), 9)
        source = (ROOT / "scripts/evaluate-google-sdp.py").read_text(encoding="utf-8")
        self.assertNotIn("LiteLLM", source)
        self.assertNotIn("gateway.complete", source)


if __name__ == "__main__":
    unittest.main()
