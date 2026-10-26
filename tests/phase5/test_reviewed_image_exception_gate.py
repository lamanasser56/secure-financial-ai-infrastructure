"""Offline tests for the two scoped App/Ops Trivy exceptions and the expiry/KEV fail-closed gate."""

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
NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
CVE = "CVE-2026-112940"


def feed(*, extra=(), released=NOW - timedelta(days=1)):
    ids = [f"CVE-2020-{n:05d}" for n in range(1000)] + list(extra)
    return {"catalogVersion": "2026.10.24", "dateReleased": released.isoformat(),
            "count": len(ids), "vulnerabilities": [{"cveID": i} for i in ids]}


def finding(advisory=CVE, severity="HIGH", package="filelock", version="3.32.7", fixed="4.2.1"):
    return {"VulnerabilityID": advisory, "Severity": severity, "PkgName": package,
            "InstalledVersion": version, "FixedVersion": fixed}


def report(image="agent-platform-app", *findings, digest=False):
    subject = (f"us-east1-docker.pkg.dev/example-project/sdp-evaluation-images/{image}@sha256:{'a' * 64}"
               if digest else f"local/{image}:{'b' * 40}")
    return subject, {"SchemaVersion": 2, "ArtifactType": "container_image", "ArtifactName": subject,
                     "Results": [{"Target": "Python", "Vulnerabilities": list(findings)}]}


class ReviewedExceptionGateTest(unittest.TestCase):
    def check(self, image, findings, *, now=NOW, kev=None, digest=False, register=REGISTER):
        subject, raw = report(image, *findings, digest=digest)
        allowed, reason, filtered = GATE.gate(raw, subject, image, kev or feed(), register, now)
        return allowed, reason, filtered, raw

    def test_only_app_and_ops_exact_finding_passes_local_and_digest(self):
        for image in ("agent-platform-app", "agent-platform-ops"):
            for digest in (False, True):
                with self.subTest(image=image, digest=digest):
                    allowed, _, filtered, raw = self.check(image, [finding()], digest=digest)
                    self.assertTrue(allowed)
                    self.assertEqual(filtered["Results"][0]["Vulnerabilities"], [])
                    self.assertEqual(raw["Results"][0]["Vulnerabilities"], [finding()])

    def test_other_images_are_never_exempted(self):
        for image in ("agent-financial", "platform-guide", "agent-platform-gateway",
                      "agent-platform-redactor", "agent-platform-database"):
            self.assertFalse(self.check(image, [finding()])[0])

    def test_declared_release_images_are_the_gate_inventory(self):
        catalog = json.loads((ROOT / "platform/image-targets.json").read_text())
        self.assertEqual(GATE.IMAGES, {entry["image"] for entry in catalog["images"]})
        with self.assertRaisesRegex(ValueError, "unknown image"):
            self.check("unlisted-service", [])

    def test_any_other_high_or_critical_still_blocks(self):
        for severity in ("HIGH", "CRITICAL"):
            with self.subTest(severity=severity):
                allowed, reason, _, _ = self.check("agent-platform-app", [finding(), finding("CVE-2026-99999", severity)])
                self.assertFalse(allowed)
                self.assertIn("CVE-2026-99999", reason)
        for changed in (finding(package="other"), finding(version="3.32.8"), finding(fixed="4.2.2"),
                        finding(severity="CRITICAL"), finding(advisory="CVE-2026-99999")):
            self.assertFalse(self.check("agent-platform-app", [changed])[0])

    def test_kev_blocks_at_every_severity_even_for_exception(self):
        for severity in ("LOW", "MEDIUM", "UNKNOWN", "HIGH", "CRITICAL"):
            with self.subTest(severity=severity):
                self.assertFalse(self.check("agent-platform-app", [finding(), finding("CVE-2026-99999", severity)],
                                            kev=feed(extra=("CVE-2026-99999",)))[0])
        self.assertFalse(self.check("agent-platform-app", [finding()], kev=feed(extra=(CVE,)))[0])

    def test_exception_expires_automatically_after_november_6(self):
        expires = NOW.replace(month=11, day=6)
        self.assertTrue(self.check("agent-platform-app", [finding()], now=expires,
                                   kev=feed(released=expires - timedelta(days=1)))[0])
        after = expires + timedelta(days=1)
        allowed, reason, _, _ = self.check("agent-platform-app", [finding()], now=after,
                                           kev=feed(released=after - timedelta(days=1)))
        self.assertFalse(allowed)
        self.assertIn(CVE, reason)
        self.assertTrue(self.check("agent-platform-app", [], now=after,
                                   kev=feed(released=after - timedelta(days=1)))[0])

    def test_tampered_register_or_stale_feed_fails_closed(self):
        wrong = json.loads(json.dumps(REGISTER))
        wrong["exceptions"][0]["expires_at"] = "2026-11-07"
        with self.assertRaises(ValueError):
            self.check("agent-platform-app", [finding()], register=wrong)
        with self.assertRaises(ValueError):
            self.check("agent-platform-app", [finding()], kev=feed(released=NOW - timedelta(days=20)))

    def test_saved_after_reports_reproduce_exact_exception_offline(self):
        for image, filename in (("agent-platform-app", "app-after.json"),
                                ("agent-platform-ops", "ops-after.json")):
            raw = json.loads((ROOT / "docs/evidence/trivy-2026-10-24" / filename).read_text())
            subject, _ = report(image)
            raw["ArtifactName"] = subject  # Historical scan used a different local tag.
            allowed, reason, filtered = GATE.gate(raw, subject, image, feed(), REGISTER, NOW)
            self.assertTrue(allowed, reason)
            self.assertFalse(any(v.get("Severity") in {"HIGH", "CRITICAL"}
                                 for r in filtered["Results"] for v in r.get("Vulnerabilities") or []))


if __name__ == "__main__":
    unittest.main()
