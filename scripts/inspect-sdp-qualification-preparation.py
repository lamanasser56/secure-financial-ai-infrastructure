#!/usr/bin/env python3
"""Offline inventory only: no client, live option, raw values or label replay."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.phase3.sdp_qualification import preparation_summary, QualificationFailure


if __name__ == "__main__":
    try:
        result = preparation_summary()
    except QualificationFailure:
        print('{"status":"blocked","reason":"qualification:invalid_input"}')
        sys.exit(1)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
