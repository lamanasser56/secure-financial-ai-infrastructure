#!/usr/bin/env python3
"""Run only the bounded synthetic tenant expense demonstration."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.agents.cli import main

if __name__ == "__main__":
    raise SystemExit(main("financial"))
