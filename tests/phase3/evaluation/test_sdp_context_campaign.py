import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "context_runner", ROOT / "scripts/evaluate-sdp-context-policy.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ContextCampaignTests(unittest.TestCase):
    def test_retained_qualification_binds_historical_subject_not_diagnostic_candidate(self):
        import hashlib

        record = json.loads(
            (ROOT / "evaluation/google-sdp-context/qualification.json").read_text()
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "evaluation/google-sdp-context/qualification.json").read_bytes()).hexdigest(),
            "b18f1f5af688e31d72458302b1c1e43b730d740b296b2a5581b0df785c0e3bbe",
        )  # Preserve the exact historical record; no ancestry/fetch dependency.
        changed = set()
        for path, expected in record["source_input_sha256"].items():
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
                changed.add(path)
        self.assertEqual(changed, {
            "runtime/phase3/google_sdp_adapter.py",
            "scripts/evaluate-sdp-context-policy.py",
            "evaluation/google-sdp-context/result.schema.json",
        })
        # Unchanged release helper rejects these stale inputs BEFORE build/auth.
        helper = (ROOT / "scripts/qualify-sdp-context-release.sh").read_text()
        self.assertIn("context image input differs from qualification", helper)
        self.assertLess(helper.index("context image input differs from qualification"),
                        helper.index('bash scripts/build-sdp-context-image.sh'))
        self.assertFalse(record["google_detection_proven"])
        self.assertFalse(record["authority_changed"])
        self.assertIsNone(record["candidate"]["registry_manifest_digest"])
        self.assertEqual(
            record["candidate"]["archive_sha256"][0],
            record["candidate"]["archive_sha256"][1],
        )

    def test_reference_results_sanitized_and_not_google_accuracy(self):
        result = runner.evaluate()
        self.assertEqual(result["outcome"], "OFFLINE_REFERENCE_PASS_GOOGLE_UNPROVEN")
        self.assertEqual(result["unexecuted"], 0)
        self.assertEqual(result["sdk_attempts"], 0)
        self.assertEqual(result["injected_attempts"], 0)
        self.assertEqual(result["google_quality"], "unmeasured")
        self.assertEqual(len(result["cases"]), 86)
        encoded = json.dumps(result)
        for forbidden in (
            "0000000000",
            "fixture@example.invalid",
            "SAR 240.00",
            "expected_spans",
            '"text"',
            "quote",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_live_requires_both_controls_and_no_unapproved_client(self):
        with patch.dict(runner.os.environ, {}, clear=True), patch.object(
            runner, "EvaluationRedactor"
        ) as client:
            with self.assertRaises(Exception):
                runner.evaluate(live=True)
            client.assert_not_called()
        with self.assertRaises(Exception):
            runner.evaluate(live=True, client=object())

    def test_failure_stops_campaign_and_never_retries(self):
        with patch.object(
            runner, "reference_spans", side_effect=TimeoutError("private")
        ) as detect:
            result = runner.evaluate()
        self.assertEqual(detect.call_count, 1)
        self.assertEqual(result["required_fail"], 1)
        self.assertEqual(result["unexecuted"], 85)
        self.assertNotIn("private", json.dumps(result))

    def test_overall_deadline_prevents_dispatch(self):
        clock = iter([0, 901])
        with patch.object(runner, "reference_spans") as detect:
            result = runner.evaluate(clock=lambda: next(clock))
        detect.assert_not_called()
        self.assertEqual(result["outcome"], "FAIL_CLOSED")

    def test_first_case_scope_and_both_live_acknowledgements(self):
        result = runner.evaluate(first_case_only=True)
        self.assertEqual(result["scope"], "context_001_diagnostic_only")
        self.assertEqual([c["case_id"] for c in result["cases"]], ["context-001"])
        self.assertEqual(result["sdk_attempts"], 0)
        self.assertEqual(result["required_pass"], 1)
        with patch.dict(runner.os.environ, {runner.ACK_ENV: runner.ACK_VALUE}, clear=True), \
             patch.object(runner, "EvaluationRedactor") as client:
            with self.assertRaises(runner.GoogleSDPFailure):
                runner.evaluate(live=True, first_case_only=True)
            client.assert_not_called()
        for key, value in (("sdk_attempts", 3), ("unexecuted", 2), ("observations", 1)):
            invalid = {**result, key: value}
            with self.assertRaises(ValueError):
                runner.validate_result(invalid)

    def test_diagnostics_are_finite_and_only_on_failure_old_evidence_stays_valid(self):
        import copy
        from runtime.phase3 import google_sdp_adapter as adapter

        schema = json.loads((runner.DIRECTORY / "result.schema.json").read_text())
        properties = schema["properties"]["cases"]["items"]["properties"]["diagnostic"]["properties"]
        for field, values in (("code", adapter.DIAGNOSTIC_CODES),
                              ("stage", adapter.DIAGNOSTIC_STAGES),
                              ("rpc_status", adapter.RPC_STATUSES)):
            self.assertEqual(set(properties[field]["enum"]), values)

        with patch.object(runner, "reference_spans", side_effect=runner.GoogleSDPFailure(
            "RPC_STATUS", "deidentify", "INVALID_ARGUMENT"
        )):
            result = runner.evaluate(first_case_only=True)
        self.assertEqual(result["cases"][0]["diagnostic"], {
            "code": "RPC_STATUS", "stage": "deidentify", "rpc_status": "INVALID_ARGUMENT"
        })
        old = copy.deepcopy(result)
        del old["cases"][0]["diagnostic"]
        runner.validate_result(old)  # Historical schema-v1 evidence remains valid.
        for change in ({"code": "raw-private"}, {"stage": "raw-private"},
                       {"rpc_status": "raw-private"}, {"message": "raw-private"}):
            invalid = copy.deepcopy(result)
            invalid["cases"][0]["diagnostic"].update(change)
            with self.assertRaises(Exception):
                runner.validate_result(invalid)
        result["cases"][0]["status"] = "PASS"
        with self.assertRaises(Exception):
            runner.validate_result(result)

    def test_supported_acceptance_separate_from_declared_unsupported(self):
        corpus = runner.load_corpus()
        self.assertTrue(
            any(c["classification"].startswith("unsupported_") for c in corpus["cases"])
        )
        self.assertEqual(2 * len(corpus["cases"]), 172)
        self.assertEqual(
            json.loads(
                (ROOT / "evaluation/google-sdp-agent/qualification.json").read_text()
            )["fixtures"]["proposed_live_cases"],
            87,
        )
