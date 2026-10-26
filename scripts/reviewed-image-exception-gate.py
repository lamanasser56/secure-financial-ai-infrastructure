#!/usr/bin/env python3
"""Check raw full-severity Trivy evidence, then remove only reviewed findings for the existing release gate.

Usage: reviewed-image-exception-gate.py RAW_REPORT SUBJECT IMAGE KEV REGISTER FILTERED_REPORT
The raw report is never modified. A missing, stale or malformed KEV feed fails closed.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {entry["image"] for entry in json.loads((ROOT / "platform/image-targets.json").read_text())["images"]}
EXCEPTION_IMAGES = {"agent-platform-app", "agent-platform-ops"}
ADVISORY = "CVE-2026-112940"
PACKAGE = "filelock"
VERSION = "3.32.7"
FIXED_VERSION = "4.2.1"
EXPIRY = date(2026, 11, 6)
LOCAL_REF = re.compile(r"^local/([a-z0-9-]+):[0-9a-f]{40}$")
REMOTE_REF = re.compile(r"^[a-z0-9.-]+/[a-z][a-z0-9-]*/sdp-evaluation-images/([a-z0-9-]+)@sha256:[0-9a-f]{64}$")


def kev_gate_module():
    spec = importlib.util.spec_from_file_location("kev_release_gate", ROOT / "scripts/kev-release-gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_register(register: dict) -> None:
    if not isinstance(register, dict) or set(register) != {"schema_version", "exceptions"} or register["schema_version"] != 1:
        raise ValueError("invalid reviewed exception register")
    entries = register["exceptions"]
    if not isinstance(entries, list) or len(entries) != 2:
        raise ValueError("expected exactly two image-scoped entries")
    expected_keys = {"image", "target", "package", "installed_version", "advisory", "severity",
                     "fixed_version", "approved_at", "expires_at", "status", "justification", "reachability_evidence"}
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != expected_keys:
            raise ValueError("invalid exception fields")
        image = entry["image"]
        if image not in EXCEPTION_IMAGES or image in seen:
            raise ValueError("invalid or duplicate image exception")
        seen.add(image)
        required = {"target": "Python", "package": PACKAGE, "installed_version": VERSION,
                    "advisory": ADVISORY, "severity": "HIGH", "fixed_version": FIXED_VERSION,
                    "expires_at": EXPIRY.isoformat(), "status": "temporary_mitigation",
                    "reachability_evidence": "docs/evidence/trivy-2026-10-24/reachability.md"}
        if any(entry.get(key) != value for key, value in required.items()):
            raise ValueError("exception scope or expiry changed")
        if date.fromisoformat(entry["approved_at"]) > EXPIRY or not entry["justification"].strip():
            raise ValueError("invalid approval or justification")
    if seen != EXCEPTION_IMAGES:
        raise ValueError("missing image exception")


def gate(report: dict, subject: str, image: str, kev: dict, register: dict,
         now: datetime) -> tuple[bool, str, dict]:
    validate_register(register)
    if image not in IMAGES:
        raise ValueError("unknown image")
    match = LOCAL_REF.fullmatch(subject) or REMOTE_REF.fullmatch(subject)
    if not match or match.group(1) != image:
        raise ValueError("image reference mismatch")
    if not isinstance(report, dict) or report.get("SchemaVersion") != 2 or report.get("ArtifactType") != "container_image" or report.get("ArtifactName") != subject:
        raise ValueError("invalid or mismatched Trivy image report")
    if not isinstance(report.get("Results"), list) or not report["Results"]:
        raise ValueError("incomplete Trivy image report")
    kev_gate = kev_gate_module()
    kev_ids = kev_gate.check_feed(kev, now)
    hits = kev_gate.kev_hits(report, kev_ids)  # All severities, before filtering.
    if hits:
        return False, f"KEV-listed finding(s): {sorted(set(hits))}", report
    if now.date() > EXPIRY and image in EXCEPTION_IMAGES:
        # Let a clean image pass after expiry, but the expired exception never applies.
        active = False
    else:
        active = image in EXCEPTION_IMAGES
    filtered = json.loads(json.dumps(report))
    blocked = []
    excepted = 0
    for result in filtered["Results"]:
        if not isinstance(result, dict) or not isinstance(result.get("Target"), str):
            raise ValueError("invalid scan target")
        vulns = result.get("Vulnerabilities") or []
        if not isinstance(vulns, list):
            raise ValueError("invalid vulnerability list")
        remaining = []
        for vuln in vulns:
            if not isinstance(vuln, dict) or not isinstance(vuln.get("VulnerabilityID"), str):
                raise ValueError("invalid finding")
            exact = (active and result["Target"] == "Python" and
                     vuln.get("VulnerabilityID") == ADVISORY and vuln.get("PkgName") == PACKAGE and
                     vuln.get("InstalledVersion") == VERSION and vuln.get("FixedVersion") == FIXED_VERSION and
                     vuln.get("Severity") == "HIGH")
            if exact:
                excepted += 1
            else:
                remaining.append(vuln)
                if vuln.get("Severity") in {"HIGH", "CRITICAL"}:
                    blocked.append(vuln["VulnerabilityID"])
        result["Vulnerabilities"] = remaining
    if excepted > 1:
        raise ValueError("duplicate excepted finding")
    if blocked:
        return False, f"unreviewed HIGH/CRITICAL finding(s): {', '.join(sorted(set(blocked)))}", filtered
    return True, f"full-severity KEV clear; {excepted} exact reviewed finding(s) accepted; expiry {EXPIRY}", filtered


def main() -> int:
    if len(sys.argv) != 7:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        report, kev, register = (json.loads(Path(p).read_text(encoding="utf-8"))
                                 for p in (sys.argv[1], sys.argv[4], sys.argv[5]))
        allowed, reason, filtered = gate(report, sys.argv[2], sys.argv[3], kev, register,
                                         datetime.now(timezone.utc))
        if allowed:
            Path(sys.argv[6]).write_text(json.dumps(filtered, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError, AttributeError) as exc:
        print(f"BLOCK: invalid release evidence ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 2
    print(("PASS: " if allowed else "BLOCK: ") + reason)
    return 0 if allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
