#!/usr/bin/env python3
"""Local artifact admission: exact generated client/engine inventory and hashes."""
import hashlib
import json
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]


def verify():
    artifact = ROOT / ".qualified"
    if artifact.is_symlink():
        raise ValueError
    record = json.loads((ROOT / "evaluation/agent-composition/generated-inputs.json").read_text())
    expected = record["sha256"]
    found = {}
    for path in artifact.rglob("*"):
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError
        found[path.relative_to(artifact).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not found or found != expected:
        raise ValueError
    print("PASS: exact generated client and native engine inputs")


if __name__ == "__main__":
    try:
        verify()
    except Exception:
        raise SystemExit("composition:generated_image_input_mismatch") from None
