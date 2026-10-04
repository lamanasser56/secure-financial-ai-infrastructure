"""Prevent stale candidate evidence or an implied authority promotion."""

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PreparationEvidenceTests(unittest.TestCase):
    def test_gateway_build_inputs_match_unpromoted_evidence(self):
        record = json.loads(
            (ROOT / "evaluation/litellm-candidate/qualification.json").read_text()
        )
        for path, expected in record["source_input_sha256"].items():
            self.assertEqual(
                hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected, path
            )
        self.assertEqual(record["designs_used"], 2)
        self.assertFalse(record["published"])
        self.assertFalse(record["signed"])
        self.assertFalse(record["authority_changed"])
        self.assertEqual(record["external_model_requests"], 0)
        candidate = record["candidate"]
        self.assertEqual(candidate["policy_exit"], 0)
        self.assertEqual(candidate["exceptions"], 0)
        self.assertEqual(candidate["vulnerabilities"].get("HIGH", 0), 0)
        self.assertEqual(candidate["vulnerabilities"].get("CRITICAL", 0), 0)
        self.assertEqual(candidate["archive_sha256"][0], candidate["archive_sha256"][1])
        self.assertIsNone(candidate["registry_manifest_digest"])
        self.assertIsNone(candidate["signature"])
        self.assertFalse(candidate["probe"]["credential_qualification"])
        self.assertFalse(candidate["probe"]["redactor_qualification"])

    def test_completed_sdp_image_and_full_campaign_evidence_are_unchanged(self):
        record = json.loads(
            (ROOT / "evaluation/google-sdp-agent/qualification.json").read_text()
        )
        for path, expected in record["image_source_input_sha256"].items():
            self.assertEqual(
                hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected, path
            )
        for path, expected in record["qualification_source_input_sha256"].items():
            self.assertEqual(
                hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected, path
            )
        self.assertEqual(record["fixtures"]["proposed_live_cases"], 87)
        self.assertEqual(record["fixtures"]["prepared_offline_cases"], 42)
        self.assertEqual(record["fixtures"]["unprepared_cases"], 45)
