#!/usr/bin/env python3
"""Validate a bounded sanitized full-campaign result; no provider or cloud access."""

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("context_campaign_validation", ROOT / "scripts/evaluate-sdp-context-policy.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def validate(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=runner._unique)
    if result.get("scope") != runner.CAMPAIGN_SCOPE:
        raise ValueError
    runner.validate_result(result)
    return {key: result[key] for key in (
        "scope", "mode", "google_quality", "authority_changed", "required_pass",
        "required_fail", "observations", "observation_failures", "operational_failures",
        "unexecuted", "sdk_attempts", "injected_attempts", "outcome"
    )}


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError
        summary = validate(sys.argv[1])
    except Exception:
        raise SystemExit("campaign result contract rejected") from None
    print(json.dumps(summary, sort_keys=True))
