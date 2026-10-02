#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
bash scripts/check-python-lock.sh
if [ "${PORTFOLIO_CHECK_GOOGLE_SDP_LOCK:-0}" = 1 ]; then
  bash scripts/check-google-sdp-lock.sh
  bash scripts/check-google-sdp-runtime-lock.sh
fi
python3 -B scripts/validate.py
python3 -B scripts/check-references.py
bash scripts/validate-google-sdp-deployment.sh
for suite in tests/phase3/runtime tests/phase3/evaluation tests/phase4/registry tests/phase4/invocation tests/phase4/governance tests/phase5; do
  python3 -B -m unittest discover -s "$suite" -p 'test_*.py'
done
