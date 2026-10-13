#!/usr/bin/env python3
"""Release gate run before an agent-platform image is signed (SC-002).

Usage: kev-release-gate.py REPORT SUBJECT KEV REGISTER

1. The CISA KEV feed must be a valid, fresh catalog (released at most MAX_FEED_AGE_DAYS ago).
2. Every finding in the full-severity Trivy report is checked against KEV *before* any severity filter:
   a KEV-listed advisory of any severity (including LOW, MEDIUM and UNKNOWN) blocks.
3. The unchanged portable policy (scripts/evaluate-container-vulnerability-policy.py) then decides
   HIGH/CRITICAL findings against the exception register.
Fail-closed: any malformed input blocks (exit 2); a policy block exits 1.
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_FEED_AGE_DAYS = 14
MIN_FEED_ENTRIES = 1000
CVE = re.compile(r"^CVE-[0-9]{4}-[0-9]{4,}$")


def load_policy():
    spec = importlib.util.spec_from_file_location(
        "vulnerability_policy", ROOT / "scripts/evaluate-container-vulnerability-policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_feed(kev: dict, now: datetime) -> set[str]:
    if not isinstance(kev, dict) or not isinstance(kev.get("catalogVersion"), str):
        raise ValueError("invalid KEV catalog")
    released = datetime.fromisoformat(str(kev.get("dateReleased", "")).replace("Z", "+00:00"))
    if released.tzinfo is None:
        raise ValueError("KEV release time has no timezone")
    age = now - released
    if age.total_seconds() < -3600:
        raise ValueError("KEV release time is in the future")
    if age.days > MAX_FEED_AGE_DAYS:
        raise ValueError("stale KEV feed")
    items = kev.get("vulnerabilities")
    if not isinstance(items, list) or len(items) < MIN_FEED_ENTRIES or kev.get("count") != len(items):
        raise ValueError("incomplete KEV feed")
    ids = set()
    for item in items:
        cve = item.get("cveID") if isinstance(item, dict) else None
        if not isinstance(cve, str) or not CVE.fullmatch(cve):
            raise ValueError("invalid KEV entry")
        ids.add(cve)
    return ids


def kev_hits(report: dict, kev_ids: set[str]) -> list[tuple[str, str]]:
    """(advisory, severity) for every KEV-listed finding, whatever its severity."""
    results = report.get("Results")
    if not isinstance(results, list) or not results:
        raise ValueError("incomplete image report")
    hits = []
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("invalid scan target")
        vulnerabilities = result.get("Vulnerabilities") or []
        if not isinstance(vulnerabilities, list):
            raise ValueError("invalid vulnerability list")
        for vuln in vulnerabilities:
            if not isinstance(vuln, dict) or not isinstance(vuln.get("VulnerabilityID"), str):
                raise ValueError("invalid finding")
            aliases = vuln.get("VendorIDs") or []
            if not isinstance(aliases, list):
                raise ValueError("invalid vendor identifiers")
            ids = {vuln["VulnerabilityID"], *(a for a in aliases if isinstance(a, str))}
            for advisory in sorted(ids & kev_ids):
                hits.append((advisory, str(vuln.get("Severity", "UNKNOWN"))))
    return hits


def gate(report: dict, subject: str, kev: dict, register: dict, now: datetime) -> tuple[bool, str]:
    if not isinstance(report, dict):
        raise ValueError("invalid Trivy image report")
    kev_ids = check_feed(kev, now)
    hits = kev_hits(report, kev_ids)
    if hits:
        listed = ", ".join(f"{a} ({s})" for a, s in sorted(set(hits)))
        return False, f"KEV-listed finding(s), any severity: {listed}"
    allowed, reason = load_policy().evaluate(report, subject, kev, register, now.date())
    return allowed, f"no KEV-listed finding (catalog {kev['catalogVersion']}); {reason}"


def main() -> int:
    if len(sys.argv) != 5:
        print("usage: kev-release-gate.py REPORT SUBJECT KEV REGISTER", file=sys.stderr)
        return 2
    try:
        report, kev, register = (json.loads(Path(p).read_text(encoding="utf-8"))
                                 for p in (sys.argv[1], sys.argv[3], sys.argv[4]))
        allowed, reason = gate(report, sys.argv[2], kev, register, datetime.now(timezone.utc))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError, AttributeError) as exc:
        print(f"BLOCK: invalid release evidence ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 2
    print(("PASS: " if allowed else "BLOCK: ") + reason)
    return 0 if allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
