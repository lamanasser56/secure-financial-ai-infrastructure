#!/usr/bin/env python3
"""Check raw full-severity Trivy evidence before the existing release gate; no exception is registered.

Usage: reviewed-image-exception-gate.py RAW_REPORT SUBJECT IMAGE KEV REGISTER FILTERED_REPORT
Any KEV-listed finding (every severity) or any HIGH/CRITICAL finding blocks. The register must be empty: the former
App/Ops filelock exception is obsolete because neither image contains filelock any more, and no exception may be
added. The raw report is never modified. A missing, stale or malformed KEV feed fails closed.
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {entry["image"] for entry in json.loads((ROOT / "platform/image-targets.json").read_text())["images"]}
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
    if register["exceptions"] != []:
        raise ValueError("no reviewed image exception is permitted")


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
    hits = kev_gate.kev_hits(report, kev_ids)  # All severities.
    if hits:
        return False, f"KEV-listed finding(s): {sorted(set(hits))}", report
    filtered = json.loads(json.dumps(report))
    blocked = []
    for result in filtered["Results"]:
        if not isinstance(result, dict) or not isinstance(result.get("Target"), str):
            raise ValueError("invalid scan target")
        vulns = result.get("Vulnerabilities") or []
        if not isinstance(vulns, list):
            raise ValueError("invalid vulnerability list")
        for vuln in vulns:
            if not isinstance(vuln, dict) or not isinstance(vuln.get("VulnerabilityID"), str):
                raise ValueError("invalid finding")
            if vuln.get("Severity") in {"HIGH", "CRITICAL"}:
                blocked.append(vuln["VulnerabilityID"])
    if blocked:
        return False, f"unreviewed HIGH/CRITICAL finding(s): {', '.join(sorted(set(blocked)))}", filtered
    return True, "full-severity KEV clear; 0 exact reviewed finding(s) accepted; no exception registered", filtered


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
