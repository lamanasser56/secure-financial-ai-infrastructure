"""Offline candidate expression checks, not Google detector accuracy."""

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]


class ObfuscatedCandidateTests(unittest.TestCase):
    def test_optional_native_sdk_shape_without_client_or_rpc(self):
        try:
            from google.cloud import dlp_v2
        except ImportError:
            self.skipTest("separate locked SDK shape gate required")
        config = json.loads(
            (
                ROOT / "evaluation/google-sdp-agent/obfuscated-email-candidate.json"
            ).read_text()
        )
        message = dlp_v2.InspectConfig(
            custom_info_types=[
                {
                    "info_type": {"name": config["custom_info_type"]},
                    "regex": {"pattern": config["pattern"]},
                    "likelihood": dlp_v2.Likelihood.VERY_LIKELY,
                }
            ],
            include_quote=False,
        )
        self.assertFalse(message.include_quote)
        self.assertEqual(message.custom_info_types[0].regex.pattern, config["pattern"])

    def test_existing_reserved_three_language_ground_truth_spans(self):
        config = json.loads(
            (
                ROOT / "evaluation/google-sdp-agent/obfuscated-email-candidate.json"
            ).read_text()
        )
        cases = json.loads(
            (ROOT / "evaluation/google-sdp-agent/offline-fixtures.json").read_text()
        )["cases"]
        selected = [c for c in cases if c["case_id"].startswith("obfuscated-")]
        self.assertEqual(len(selected), 3)
        for case in selected:
            matches = [
                (m.start(), m.end())
                for m in re.finditer(config["pattern"], case["text"])
            ]
            self.assertEqual(
                matches, [(x["start"], x["end"]) for x in case["expected_spans"]]
            )
        self.assertEqual(config["status"], "candidate_unqualified_unwired")

    def test_matched_negatives_do_not_become_positive_fixtures(self):
        config = json.loads(
            (
                ROOT / "evaluation/google-sdp-agent/obfuscated-email-candidate.json"
            ).read_text()
        )
        for value in (
            "example [dot] invalid",
            "fixture [at] example",
            "[at] [dot]",
            "SAR 240.00; 2026-01",
        ):
            self.assertIsNone(re.search(config["pattern"], value))
