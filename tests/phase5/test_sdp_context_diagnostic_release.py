"""Offline diagnostic release admission; no image build or provider call."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml
import jsonschema


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/qualify-sdp-context-diagnostic-release.sh"
WORKFLOW = ROOT / ".github/workflows/release-google-sdp-evaluation.yml"
HISTORICAL = ROOT / "evaluation/google-sdp-context/qualification.json"
DIAGNOSTIC = ROOT / "evaluation/google-sdp-context/diagnostic-qualification.json"


class DiagnosticReleaseTests(unittest.TestCase):
    def test_actual_qualified_diagnostic_record_binds_current_exact_inputs_and_limits(self):
        historical = json.loads(HISTORICAL.read_text())
        record = json.loads(DIAGNOSTIC.read_text())
        self.assertEqual(record["source_baseline"], "4df3686c708d0e00107a3226d18ff5b2536ee53d")
        self.assertEqual(set(record["source_input_sha256"]), set(historical["source_input_sha256"]))
        self.assertEqual(len(record["source_input_sha256"]), 14)
        for name, expected in record["source_input_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected, name)
        self.assertNotEqual(record["source_input_sha256"]["runtime/phase3/google_sdp_adapter.py"],
                            historical["source_input_sha256"]["runtime/phase3/google_sdp_adapter.py"])
        expected = {
            "schema_version": 1,
            "evaluation_profile": "context-001-diagnostic-v1",
            "scope": "context_001_diagnostic_only",
            "case_id": "context-001",
            "sdk_attempt_ceiling": 2,
            "metadata_attempts": 0,
            "retries": 0,
            "job_deadline_seconds": 120,
            "max_input_bytes": 4096,
            "max_output_bytes": 4096,
            "rpc_timeout_seconds": 3,
            "redaction_deadline_seconds": 8,
            "published": False,
            "signed": False,
            "authority_changed": False,
            "google_detection_proven": False,
        }
        for name, value in expected.items():
            self.assertIs(type(record[name]), type(value), name)
            self.assertEqual(record[name], value, name)
        self.assertEqual(record["acknowledgements"], {
            "PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK": "I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY",
            "PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK": "I_ACKNOWLEDGE_CONTEXT_001_ONLY_TWO_ATTEMPTS",
        })
        candidate = record["candidate"]
        self.assertNotEqual(candidate["configuration_digest"], historical["candidate"]["configuration_digest"])
        self.assertRegex(candidate["configuration_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(candidate["archive_sha256"][0], candidate["archive_sha256"][1])
        self.assertTrue(candidate["reproducible_archives"])
        self.assertEqual(candidate["user"], "65532:65532")
        self.assertEqual(candidate["architecture"], "amd64")
        self.assertEqual((candidate["policy_exit"], candidate["exceptions"]), (0, 0))
        self.assertIsNone(candidate["registry_manifest_digest"])
        self.assertIsNone(candidate["signature"])
        self.assertGreater(candidate["sbom_components"], 0)
        self.assertEqual(candidate["vulnerabilities"].get("HIGH", 0), 0)
        self.assertEqual(candidate["vulnerabilities"].get("CRITICAL", 0), 0)
        self.assertEqual(candidate["tools"], {
            "buildx": "0.30.1", "buildkit": "0.33.1", "trivy": "0.72.0", "syft": "1.44.0",
        })
        for name, expected in candidate["evidence_sha256"].items():
            self.assertRegex(expected, r"^[0-9a-f]{64}$", name)
        for name in ("sbom.json", "trivy-original.json", "trivy-policy-copy.json", "image-offline-result.json"):
            self.assertNotEqual(candidate["evidence_sha256"][name],
                                historical["candidate"]["evidence_sha256"][name], name)

    def test_actual_first_case_offline_result_matches_qualified_subject_and_schema(self):
        process = subprocess.run([sys.executable, str(ROOT / "scripts/evaluate-sdp-context-policy.py"),
                                  "--diagnostic-first-case"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        schema = json.loads((ROOT / "evaluation/google-sdp-context/result.schema.json").read_text())
        jsonschema.Draft202012Validator(schema).validate(result)
        self.assertEqual(result["scope"], "context_001_diagnostic_only")
        self.assertEqual(result["mode"], "offline_reference")
        self.assertEqual(result["google_quality"], "unmeasured")
        self.assertFalse(result["authority_changed"])
        self.assertEqual([case["case_id"] for case in result["cases"]], ["context-001"])
        self.assertEqual((result["required_pass"], result["required_fail"], result["observations"],
                          result["sdk_attempts"], result["injected_attempts"], result["unexecuted"]),
                         (1, 0, 0, 0, 0, 0))
        record = json.loads(DIAGNOSTIC.read_text())
        self.assertEqual(hashlib.sha256(process.stdout.encode()).hexdigest(),
                         record["candidate"]["evidence_sha256"]["image-offline-result.json"])

    def test_distinct_profile_and_both_jobs_restrict_exact_release_image(self):
        workflow = yaml.safe_load(WORKFLOW.read_text())
        trigger = workflow.get("on", workflow.get(True))
        self.assertEqual(set(trigger), {"workflow_dispatch"})
        profiles = trigger["workflow_dispatch"]["inputs"]["evaluation_profile"]
        self.assertIn("context-001-diagnostic-v1", profiles["options"])
        self.assertEqual(profiles["default"], "seed")
        self.assertEqual(workflow["permissions"], {})
        self.assertEqual(workflow["jobs"]["qualify"]["permissions"], {"contents": "read"})
        self.assertEqual(workflow["jobs"]["publish"]["permissions"],
                         {"contents": "read", "id-token": "write"})
        for job_name in ("qualify", "publish"):
            steps = workflow["jobs"][job_name]["steps"]
            check = next(step["run"] for step in steps
                         if "APPROVED_COMMIT" in step.get("env", {}))
            self.assertIn(
                'context-001-diagnostic-v1) [[ "$IMAGE_NAME" == google-sdp-context-diagnostic '
                '&& "$ARTIFACT_REPOSITORY" == sdp-evaluation-images ]] ;;', check)
            self.assertIn('[[ "$GITHUB_RUN_ATTEMPT" == 1 ]]', check)
            for step in steps:
                if "uses" in step:
                    self.assertRegex(step["uses"], r"^[\w-]+/[\w-]+@[0-9a-f]{40}$")
        wrapper = (ROOT / "scripts/build-google-sdp-evaluation-image.sh").read_text()
        self.assertIn('exec bash scripts/qualify-sdp-context-diagnostic-release.sh "$buildx_builder"', wrapper)
        self.assertIn('exec bash scripts/qualify-sdp-context-release.sh "$buildx_builder"', wrapper)

    def test_historical_subject_unchanged_diagnostic_gate_is_offline_and_separate(self):
        self.assertEqual(hashlib.sha256(HISTORICAL.read_bytes()).hexdigest(),
                         "b18f1f5af688e31d72458302b1c1e43b730d740b296b2a5581b0df785c0e3bbe")
        helper = HELPER.read_text()
        self.assertIn("diagnostic-qualification.json", helper)
        self.assertLess(helper.index("diagnostic image input differs from qualification"),
                        helper.index("bash scripts/build-sdp-context-image.sh"))
        self.assertIn('[[ "$configuration" ==', helper)
        self.assertIn("--diagnostic-first-case", helper)
        self.assertIn("--network none --read-only --cap-drop ALL", helper)
        self.assertNotIn("import jsonschema", helper)
        self.assertIn("validates its result schema before emitting JSON", helper)
        self.assertNotIn("--live", helper)
        self.assertNotRegex(helper, r"docker\s+push|cosign\s+sign|gcloud\s|kubectl\s")

    def test_mutated_scope_limits_hashes_and_candidate_fail_before_builder(self):
        historical = json.loads(HISTORICAL.read_text())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            shutil.copyfile(HELPER, root / "scripts" / HELPER.name)
            hashes = {}
            for name in historical["source_input_sha256"]:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
                hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
            record = {
                "schema_version": 1,
                "evaluation_profile": "context-001-diagnostic-v1",
                "scope": "context_001_diagnostic_only",
                "case_id": "context-001",
                "sdk_attempt_ceiling": 2,
                "metadata_attempts": 0,
                "retries": 0,
                "job_deadline_seconds": 120,
                "max_input_bytes": 4096,
                "max_output_bytes": 4096,
                "rpc_timeout_seconds": 3,
                "redaction_deadline_seconds": 8,
                "acknowledgements": {
                    "PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK": "I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY",
                    "PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK": "I_ACKNOWLEDGE_CONTEXT_001_ONLY_TWO_ATTEMPTS",
                },
                "published": False,
                "signed": False,
                "authority_changed": False,
                "google_detection_proven": False,
                "source_input_sha256": hashes,
                "candidate": {
                    "policy_exit": 0,
                    "exceptions": 0,
                    "reproducible_archives": True,
                    "archive_sha256": ["a" * 64, "a" * 64],
                    "vulnerabilities": {"HIGH": 0, "CRITICAL": 0},
                    "registry_manifest_digest": None,
                    "signature": None,
                    "configuration_digest": "sha256:" + "a" * 64,
                },
            }
            tools = root / "tools"
            tools.mkdir()
            docker = tools / "docker"
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DIAGNOSTIC_TEST_DOCKER_CALLS"\nexit 91\n')
            docker.chmod(0o700)
            calls = root / "docker-calls"
            environment = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}",
                           "DIAGNOSTIC_TEST_DOCKER_CALLS": str(calls)}
            record_path = root / "evaluation/google-sdp-context/diagnostic-qualification.json"

            def run(candidate):
                record_path.write_text(json.dumps(candidate))
                calls.write_text("")
                return subprocess.run(["bash", str(root / "scripts" / HELPER.name), "diagnostic-test"],
                                      cwd=root, env=environment, capture_output=True, text=True)

            # The complete synthetic admission fixture reaches the dummy builder,
            # which exits before any build. Negative fixtures must never reach it.
            valid = run(record)
            self.assertNotEqual(valid.returncode, 0)
            self.assertIn("buildx inspect", calls.read_text())
            mutations = [
                ("scope", "full_campaign"), ("case_id", "context-002"),
                ("evaluation_profile", "context-pattern-v1"),
                ("sdk_attempt_ceiling", 172), ("metadata_attempts", 1),
                ("retries", 1), ("job_deadline_seconds", 900),
                ("sdk_attempt_ceiling", True), ("authority_changed", True),
                ("published", True), ("signed", True), ("google_detection_proven", True),
                ("max_input_bytes", 4097), ("max_output_bytes", 4097),
                ("rpc_timeout_seconds", 4), ("redaction_deadline_seconds", 9),
            ]
            for key, value in mutations:
                altered = deepcopy(record)
                altered[key] = value
                with self.subTest(key=key, value=value):
                    self.assertNotEqual(run(altered).returncode, 0)
                    self.assertEqual(calls.read_text(), "")
            for mutation in ("missing_ack", "changed_ack", "extra_ack", "missing_input", "changed_input", "mutable_configuration", "different_archives",
                             "high", "critical", "policy_failure", "exception", "not_reproducible"):
                altered = deepcopy(record)
                candidate = altered["candidate"]
                if mutation == "missing_ack":
                    del altered["acknowledgements"]["PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK"]
                elif mutation == "changed_ack":
                    altered["acknowledgements"]["PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK"] = "OTHER"
                elif mutation == "extra_ack":
                    altered["acknowledgements"]["OTHER"] = "OTHER"
                elif mutation == "missing_input":
                    del altered["source_input_sha256"]["runtime/phase3/google_sdp_adapter.py"]
                elif mutation == "changed_input":
                    altered["source_input_sha256"]["runtime/phase3/google_sdp_adapter.py"] = "0" * 64
                elif mutation == "mutable_configuration":
                    candidate["configuration_digest"] = "image:latest"
                elif mutation == "different_archives":
                    candidate["archive_sha256"][1] = "b" * 64
                elif mutation in {"high", "critical"}:
                    candidate["vulnerabilities"][mutation.upper()] = 1
                elif mutation == "policy_failure":
                    candidate["policy_exit"] = 1
                elif mutation == "exception":
                    candidate["exceptions"] = 1
                else:
                    candidate["reproducible_archives"] = False
                with self.subTest(mutation=mutation):
                    self.assertNotEqual(run(altered).returncode, 0)
                    self.assertEqual(calls.read_text(), "")


if __name__ == "__main__":
    unittest.main()
