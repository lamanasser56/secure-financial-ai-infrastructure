"""Static release-boundary checks for the disabled synthetic evaluation image."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "docker/google-sdp-evaluation/Dockerfile"
RECORD = ROOT / "docker/google-sdp-evaluation/candidates.json"
LOCK = ROOT / "requirements-google-sdp-runtime.txt"
BUILD = ROOT / "scripts/build-google-sdp-evaluation-image.sh"
REF = re.compile(r"^[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$")
CANDIDATE_FIELDS = {
    "source", "tag", "digest", "architecture", "compressed_size_bytes",
    "uncompressed_size_bytes", "high_fixable", "high_unfixable",
    "critical_fixable", "critical_unfixable", "result", "reason",
}


class GoogleSDPEvaluationImageTests(unittest.TestCase):
    def test_dockerfile_uses_exact_immutable_bases_and_nonroot_runtime(self):
        text = DOCKERFILE.read_text(encoding="utf-8")
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        bases = re.findall(r"^FROM\s+(\S+)", text, re.MULTILINE)
        self.assertEqual(bases, [record["selected"]["builder"], record["selected"]["runtime"]])
        self.assertEqual(len(bases), 2)
        self.assertTrue(all(REF.fullmatch(base) for base in bases))
        self.assertNotRegex(text.lower(), r"\blatest\b")
        self.assertIn("USER 65532:65532", text)
        self.assertNotRegex(text, r"(?m)^\s*(?:EXPOSE|HEALTHCHECK|ARG)\b")
        self.assertIn('CMD []', text)
        self.assertIn('ENTRYPOINT ["/usr/local/bin/python3.12", "/app/scripts/evaluate-google-sdp.py"]', text)
        self.assertIn("--require-hashes", text)
        self.assertNotRegex(text, r"(?i)project-[a-f0-9-]{20,}|GOOGLE_APPLICATION_CREDENTIALS|(?:^|\s)ENV\s+.*(?:KEY|TOKEN|SECRET)")
        self.assertNotIn("presidio", text.lower())
        self.assertNotIn("litellm", text.lower())

    def test_runtime_lock_excludes_development_and_unrelated_providers(self):
        text = LOCK.read_text(encoding="utf-8").lower()
        packages = set(re.findall(r"(?m)^([a-z0-9][a-z0-9_-]*)==", text))
        self.assertIn("jsonschema", packages)
        self.assertIn("google-cloud-dlp", packages)
        self.assertFalse(packages & {
            "pytest", "pip-tools", "actionlint-py", "pymarkdownlnt",
            "shellcheck-py", "yamllint", "presidio-analyzer", "presidio-anonymizer",
            "litellm", "boto3", "azure-ai-textanalytics",
        })
        self.assertTrue(all("--hash=sha256:" in block for block in re.split(r"(?m)^(?=[a-z0-9][a-z0-9_-]*==)", text)[1:]))

    def test_candidate_record_is_closed_and_digest_pinned(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertEqual(set(record), {"schema_version", "selected", "candidates", "qualification"})
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(set(record["selected"]), {"builder", "runtime"})
        self.assertGreaterEqual(len(record["candidates"]), 3)
        known = set()
        for item in record["candidates"]:
            self.assertEqual(set(item), CANDIDATE_FIELDS)
            self.assertEqual(item["architecture"], "linux/amd64")
            immutable = item["tag"] + "@" + item["digest"]
            self.assertRegex(immutable, REF)
            self.assertNotIn(":latest", immutable)
            known.add(immutable)
        self.assertIn(record["selected"]["builder"], known)
        self.assertIn(record["selected"]["runtime"], known)

    def test_eligible_record_requires_digest_linked_policy_evidence(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        evidence = record["qualification"]
        self.assertIsInstance(evidence, dict)
        self.assertEqual(set(evidence), {
            "decision", "image_subject", "image_id", "trivy_report_sha256",
            "image_size_bytes", "sbom_package_count", "syft_version",
            "trivy_version", "offline_validation", "sbom_sha256",
            "kev_feed_date", "trivy_db_updated_at",
            "high_fixable", "high_unfixable", "critical_fixable",
            "critical_unfixable", "policy_result",
            "image_config_digest", "reproducible_build",
        })
        self.assertEqual(evidence["decision"], "eligible")
        self.assertRegex(evidence["image_subject"], REF)
        self.assertRegex(evidence["image_id"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(evidence["image_config_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(evidence["reproducible_build"], "fresh_cache_configuration_match")
        self.assertGreater(evidence["image_size_bytes"], 0)
        self.assertGreater(evidence["sbom_package_count"], 0)
        self.assertEqual(evidence["offline_validation"], "schema_valid_network_disabled")
        for key in ("trivy_report_sha256", "sbom_sha256"):
            self.assertRegex(evidence[key], r"^sha256:[0-9a-f]{64}$")
        for key in ("high_fixable", "high_unfixable", "critical_fixable", "critical_unfixable"):
            self.assertEqual(evidence[key], 0)
        self.assertEqual(evidence["policy_result"], "PASS: accepted 0 exact finding(s); no unreviewed HIGH/CRITICAL finding")

    def test_build_script_has_offline_default_and_no_push(self):
        self.assertIn("--build-arg SOURCE_DATE_EPOCH=0", BUILD.read_text(encoding="utf-8"))
        text = BUILD.read_text(encoding="utf-8")
        self.assertIn("--network none", text)
        self.assertIn("--read-only", text)
        self.assertIn("--platform linux/amd64", text)
        self.assertIn("docker buildx build", text)
        self.assertIn("SOURCE_DATE_EPOCH=0", text)
        self.assertIn("rewrite-timestamp=true", text)
        self.assertIn("docker load -i", text)
        self.assertIn("docker export", text)
        self.assertNotRegex(text, r"(?m)^\s*docker\s+push\b|--push\b")
        self.assertNotIn("--live", text)
        self.assertNotIn("presidio", text.lower())
        self.assertNotIn("litellm", text.lower())


if __name__ == "__main__":
    unittest.main()
