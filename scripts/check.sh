#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
python3 -B scripts/validate.py
for suite in tests/phase3/runtime tests/phase4/registry tests/phase4/invocation tests/phase4/governance tests/phase5; do
  python3 -B -m unittest discover -s "$suite" -p 'test_*.py'
done
