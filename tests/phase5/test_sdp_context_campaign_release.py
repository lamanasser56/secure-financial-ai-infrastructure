"""Full campaign admission rejects changed scope before Docker/authentication."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/qualify-sdp-context-release.sh"
RECORD = ROOT / "evaluation/google-sdp-context/campaign-qualification.json"


class CampaignReleaseTests(unittest.TestCase):
    def test_fresh_record_binds_all_current_inputs_and_separate_historical_records(self):
        record = json.loads(RECORD.read_text())
        historical = json.loads((RECORD.parent / "qualification.json").read_text())
        diagnostic = json.loads((RECORD.parent / "diagnostic-qualification.json").read_text())
        self.assertEqual(set(record["source_input_sha256"]), set(historical["source_input_sha256"]))
        self.assertEqual(len(record["source_input_sha256"]), 14)
        for path, expected in record["source_input_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected, path)
        self.assertEqual(record["source_input_sha256"]["runtime/phase3/google_sdp_adapter.py"],
                         diagnostic["source_input_sha256"]["runtime/phase3/google_sdp_adapter.py"])
        for name in ("configuration_digest", "archive_sha256"):
            self.assertNotEqual(record["candidate"][name], diagnostic["candidate"][name])
        self.assertEqual(record["candidate"]["archive_sha256"][0], record["candidate"]["archive_sha256"][1])
        self.assertEqual(record["candidate"]["secret_scanning"]["image_filesystem_findings"], 0)
        self.assertEqual((record["required_cases"], record["observation_cases"], record["sdk_attempt_ceiling"]), (70, 16, 172))
        self.assertEqual((record["metadata_attempts"], record["retries"]), (0, 0))
        self.assertFalse(record["published"])
        self.assertFalse(record["signed"])
        self.assertFalse(record["authority_changed"])
        self.assertFalse(record["google_detection_proven"])
        self.assertIsNone(record["candidate"]["registry_manifest_digest"])
        self.assertIsNone(record["candidate"]["signature"])
        self.assertEqual(record["candidate"]["vulnerabilities"].get("HIGH", 0), 0)
        self.assertEqual(record["candidate"]["vulnerabilities"].get("CRITICAL", 0), 0)

    def test_scope_hash_policy_and_limits_reject_before_build(self):
        record = json.loads(RECORD.read_text())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in ["scripts/qualify-sdp-context-release.sh", *record["source_input_sha256"]]:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, target)
            tools = root / "tools"
            tools.mkdir()
            (tools / "docker").write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CAMPAIGN_DOCKER_CALLS"\nexit 91\n')
            (tools / "docker").chmod(0o700)
            calls = root / "docker-calls"
            environment = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}", "CAMPAIGN_DOCKER_CALLS": str(calls)}

            def run(value):
                (root / "evaluation/google-sdp-context/campaign-qualification.json").write_text(json.dumps(value))
                calls.write_text("")
                return subprocess.run(["bash", "scripts/qualify-sdp-context-release.sh", "campaign-test"],
                                      cwd=root, env=environment, capture_output=True, text=True)

            self.assertNotEqual(run(record).returncode, 0)
            self.assertIn("buildx inspect", calls.read_text())
            for key, value in (("scope", "context_001_diagnostic_only"), ("evaluation_profile", "seed"),
                               ("required_cases", 69), ("observation_cases", 0), ("sdk_attempt_ceiling", 173),
                               ("metadata_attempts", 1), ("retries", 1), ("job_deadline_seconds", 120),
                               ("max_input_bytes", 4097), ("max_output_bytes", 4097),
                               ("rpc_timeout_seconds", 4), ("redaction_deadline_seconds", 9),
                               ("sdk_attempt_ceiling", True), ("authority_changed", True),
                               ("published", True), ("signed", True), ("google_detection_proven", True),
                               ("corpus_sha256", "a" * 64), ("policy_sha256", "a" * 64)):
                invalid = deepcopy(record)
                invalid[key] = value
                with self.subTest(key=key):
                    self.assertNotEqual(run(invalid).returncode, 0)
                self.assertEqual(calls.read_text(), "", key)
            for mutation in ("ack", "extra_input", "input_hash", "archive", "config", "high", "exception", "sbom", "secret"):
                invalid = deepcopy(record)
                candidate = invalid["candidate"]
                if mutation == "ack":
                    invalid["acknowledgements"]["PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK"] = "OTHER"
                elif mutation == "extra_input":
                    invalid["source_input_sha256"]["arbitrary"] = "a" * 64
                elif mutation == "input_hash":
                    invalid["source_input_sha256"]["scripts/evaluate-sdp-context-policy.py"] = "a" * 64
                elif mutation == "archive":
                    candidate["archive_sha256"][1] = "b" * 64
                elif mutation == "config":
                    candidate["configuration_digest"] = "image:latest"
                elif mutation == "high":
                    candidate["vulnerabilities"]["HIGH"] = 1
                elif mutation == "exception":
                    candidate["exceptions"] = 1
                elif mutation == "sbom":
                    candidate["sbom_components"] = 0
                else:
                    candidate["secret_scanning"]["image_filesystem_findings"] = 1
                with self.subTest(mutation=mutation):
                    self.assertNotEqual(run(invalid).returncode, 0)
                    self.assertEqual(calls.read_text(), "")
