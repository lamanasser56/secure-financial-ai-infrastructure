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
    def test_context_qualification_binds_every_current_image_input(self):
        import hashlib

        record = json.loads(
            (ROOT / "evaluation/google-sdp-context/qualification.json").read_text()
        )
        for path, expected in record["source_input_sha256"].items():
            self.assertEqual(
                hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected, path
            )
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
