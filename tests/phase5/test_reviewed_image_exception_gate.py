"""Offline tests for the exception-free full-severity Trivy/KEV pre-gate (the App/Ops filelock exception is removed)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("reviewed_gate", ROOT / "scripts/reviewed-image-exception-gate.py")
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
REGISTER = json.loads((ROOT / "policy/reviewed-image-exceptions.json").read_text())
NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
FILELOCK = "CVE-2026-112940"


def feed(*, extra=(), released=NOW - timedelta(days=1)):
    ids = [f"CVE-2020-{n:05d}" for n in range(1000)] + list(extra)
    return {"catalogVersion": "2026.10.26", "dateReleased": released.isoformat(),
            "count": len(ids), "vulnerabilities": [{"cveID": i} for i in ids]}


def finding(advisory="CVE-2026-50001", severity="LOW", package="libc6", version="2.41-12", fixed=""):
    return {"VulnerabilityID": advisory, "Severity": severity, "PkgName": package,
            "InstalledVersion": version, "FixedVersion": fixed}


def report(image="agent-platform-app", *findings, digest=False):
    subject = (f"us-east1-docker.pkg.dev/example-project/sdp-evaluation-images/{image}@sha256:{'a' * 64}"
               if digest else f"local/{image}:{'b' * 40}")
    return subject, {"SchemaVersion": 2, "ArtifactType": "container_image", "ArtifactName": subject,
                     "Results": [{"Target": "Python", "Vulnerabilities": list(findings)}]}


class ExceptionFreeGateTest(unittest.TestCase):
    def check(self, image, findings, *, now=NOW, kev=None, digest=False, register=REGISTER):
        subject, raw = report(image, *findings, digest=digest)
        allowed, reason, filtered = GATE.gate(raw, subject, image, kev or feed(), register, now)
        return allowed, reason, filtered, raw

    def test_register_is_empty_and_identical_to_the_release_gate_register(self):
        self.assertEqual(REGISTER, {"schema_version": 1, "exceptions": []})
        self.assertEqual(REGISTER, json.loads((ROOT / "policy/empty-exceptions.json").read_text()))

    def test_any_exception_entry_is_rejected(self):
        old = {"image": "agent-platform-app", "target": "Python", "package": "filelock", "installed_version": "3.32.7",
               "advisory": FILELOCK, "severity": "HIGH", "fixed_version": "4.2.1", "approved_at": "2026-10-25",
               "expires_at": "2026-11-06", "status": "temporary_mitigation", "justification": "x",
               "reachability_evidence": "docs/evidence/trivy-2026-10-24/reachability.md"}
        for register in ({"schema_version": 1, "exceptions": [old]}, {"schema_version": 2, "exceptions": []},
                         {"schema_version": 1}, {"schema_version": 1, "exceptions": [], "extra": 1}):
            with self.subTest(register=register):
                with self.assertRaises(ValueError):
                    self.check("agent-platform-app", [], register=register)

    def test_clean_and_low_or_medium_findings_pass_for_every_image_local_and_digest(self):
        for image in sorted(GATE.IMAGES):
            for digest in (False, True):
                with self.subTest(image=image, digest=digest):
                    allowed, reason, filtered, raw = self.check(image, [finding(), finding(severity="MEDIUM")],
                                                                digest=digest)
                    self.assertTrue(allowed, reason)
                    self.assertIn("0 exact reviewed finding(s) accepted", reason)
                    self.assertEqual(filtered, raw)

    def test_the_former_filelock_finding_and_any_high_or_critical_block_every_image(self):
        former = finding(FILELOCK, "HIGH", "filelock", "3.32.7", "4.2.1")
        for image in sorted(GATE.IMAGES):
            for item in (former, finding(severity="HIGH"), finding(severity="CRITICAL")):
                with self.subTest(image=image, severity=item["Severity"], package=item["PkgName"]):
                    allowed, reason, _, _ = self.check(image, [item])
                    self.assertFalse(allowed)
                    self.assertIn(item["VulnerabilityID"], reason)

    def test_declared_release_images_are_the_gate_inventory(self):
        catalog = json.loads((ROOT / "platform/image-targets.json").read_text())
        self.assertEqual(GATE.IMAGES, {entry["image"] for entry in catalog["images"]})
        with self.assertRaisesRegex(ValueError, "unknown image"):
            self.check("unlisted-service", [])

    def test_kev_blocks_at_every_severity(self):
        for severity in ("LOW", "MEDIUM", "UNKNOWN", "HIGH", "CRITICAL"):
            with self.subTest(severity=severity):
                self.assertFalse(self.check("agent-platform-app", [finding("CVE-2026-99999", severity)],
                                            kev=feed(extra=("CVE-2026-99999",)))[0])

    def test_stale_feed_or_mismatched_subject_fails_closed(self):
        with self.assertRaises(ValueError):
            self.check("agent-platform-app", [], kev=feed(released=NOW - timedelta(days=20)))
        subject, raw = report("agent-platform-app")
        with self.assertRaisesRegex(ValueError, "image reference mismatch"):
            GATE.gate(raw, subject, "agent-platform-ops", feed(), REGISTER, NOW)

    def test_historical_app_and_ops_reports_with_filelock_now_block(self):
        for image, filename in (("agent-platform-app", "app-after.json"), ("agent-platform-ops", "ops-after.json")):
            raw = json.loads((ROOT / "docs/evidence/trivy-2026-10-24" / filename).read_text())
            subject, _ = report(image)
            raw["ArtifactName"] = subject  # Historical scan used a different local tag.
            allowed, reason, _ = GATE.gate(raw, subject, image, feed(), REGISTER, NOW)
            self.assertFalse(allowed)
            self.assertIn(FILELOCK, reason)


if __name__ == "__main__":
    unittest.main()
