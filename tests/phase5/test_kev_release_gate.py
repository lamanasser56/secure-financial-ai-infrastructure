"""Synthetic tests for the pre-signing KEV release gate (SC-002); no network, no real feed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("kev_release_gate", ROOT / "scripts/kev-release-gate.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
SUBJECT = "registry.invalid/agent@sha256:" + "b" * 64
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
REGISTER = {"schema_version": 1, "exceptions": []}
LISTED = "CVE-2026-99999"


def feed(*, released=NOW - timedelta(days=1), extra=(LISTED,)):
    ids = [f"CVE-2020-{n:05d}" for n in range(1000)] + list(extra)
    return {"catalogVersion": "2026.10.12", "dateReleased": released.isoformat().replace("+00:00", "Z"),
            "count": len(ids), "vulnerabilities": [{"cveID": i} for i in ids]}


def report(*findings):
    return {"SchemaVersion": 2, "ArtifactType": "container_image", "ArtifactName": SUBJECT,
            "Results": [{"Target": "debian:12", "Vulnerabilities": [
                {"VulnerabilityID": advisory, "PkgName": "lib", "InstalledVersion": "1.0", "FixedVersion": "",
                 "Severity": severity} for advisory, severity in findings]}]}


class KevReleaseGateTest(unittest.TestCase):
    def test_clean_report_passes(self):
        allowed, reason = GATE.gate(report(), SUBJECT, feed(), REGISTER, NOW)
        self.assertTrue(allowed, reason)

    def test_unlisted_low_and_medium_pass(self):
        allowed, _ = GATE.gate(report(("CVE-2026-00001", "LOW"), ("CVE-2026-00002", "MEDIUM")),
                               SUBJECT, feed(), REGISTER, NOW)
        self.assertTrue(allowed)

    def test_kev_blocks_at_every_severity(self):
        for severity in ("LOW", "MEDIUM", "UNKNOWN", "HIGH", "CRITICAL"):
            with self.subTest(severity=severity):
                allowed, reason = GATE.gate(report((LISTED, severity)), SUBJECT, feed(), REGISTER, NOW)
                self.assertFalse(allowed)
                self.assertIn(LISTED, reason)

    def test_kev_alias_in_vendor_ids_blocks(self):
        rep = report(("GHSA-aaaa-bbbb-cccc", "LOW"))
        rep["Results"][0]["Vulnerabilities"][0]["VendorIDs"] = [LISTED]
        self.assertFalse(GATE.gate(rep, SUBJECT, feed(), REGISTER, NOW)[0])

    def test_unlisted_high_still_blocked_by_policy(self):
        allowed, reason = GATE.gate(report(("CVE-2026-00003", "HIGH")), SUBJECT, feed(), REGISTER, NOW)
        self.assertFalse(allowed)
        self.assertIn("HIGH/CRITICAL", reason)

    def test_stale_feed_fails_closed(self):
        with self.assertRaises(ValueError):
            GATE.gate(report(), SUBJECT, feed(released=NOW - timedelta(days=GATE.MAX_FEED_AGE_DAYS + 1)),
                      REGISTER, NOW)

    def test_future_feed_fails_closed(self):
        with self.assertRaises(ValueError):
            GATE.gate(report(), SUBJECT, feed(released=NOW + timedelta(days=2)), REGISTER, NOW)

    def test_truncated_or_inconsistent_feed_fails_closed(self):
        small = feed()
        small["vulnerabilities"] = small["vulnerabilities"][:10]
        small["count"] = 10
        bad_count = feed()
        bad_count["count"] += 1
        bad_id = feed(extra=("not-a-cve",))
        for kev in (small, bad_count, bad_id, {"vulnerabilities": []}):
            with self.subTest(kev=str(kev)[:40]), self.assertRaises(ValueError):
                GATE.gate(report(), SUBJECT, kev, REGISTER, NOW)

    def test_subject_mismatch_fails_closed(self):
        with self.assertRaises(ValueError):
            GATE.gate(report(), "registry.invalid/other@sha256:" + "c" * 64, feed(), REGISTER, NOW)

    def test_empty_report_fails_closed(self):
        rep = report()
        rep["Results"] = []
        with self.assertRaises(ValueError):
            GATE.gate(rep, SUBJECT, feed(), REGISTER, NOW)


if __name__ == "__main__":
    unittest.main()
