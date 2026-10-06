#!/usr/bin/env python3
"""Validate a bounded sanitized AM-R4 composite campaign result; no provider or cloud access.

Separate from validate-sdp-context-campaign-result.py, which still governs Google-only
records unchanged. A composite PASS is never a Google qualification.
"""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("composite_campaign", ROOT / "scripts/evaluate-composite-email-campaign.py")
program = importlib.util.module_from_spec(spec)
spec.loader.exec_module(program)


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def validate(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    program.validate_result(result)
    return {key: result[key] for key in (
        "scope", "provider_scope", "mode", "google_qualification_claimed", "authority_changed", "required_pass",
        "required_fail", "observations", "observation_failures", "operational_failures", "unexecuted",
        "sdk_attempts", "injected_attempts", "metadata_sdk_attempts", "deterministic_email_cases", "outcome")}


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError
        summary = validate(sys.argv[1])
    except Exception:
        raise SystemExit("composite campaign result contract rejected") from None
    print(json.dumps(summary, sort_keys=True))
