#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
bash scripts/check-python-lock.sh
if [ "${PORTFOLIO_CHECK_GOOGLE_SDP_LOCK:-0}" = 1 ]; then
  bash scripts/check-google-sdp-lock.sh
  bash scripts/check-google-sdp-runtime-lock.sh
fi
if [ "${PORTFOLIO_CHECK_AGENT_COMPOSITION_LOCK:-0}" = 1 ]; then
  bash scripts/check-agent-composition-lock.sh
fi
python3 -B scripts/validate.py
python3 -B scripts/check-references.py
for suite in tests/phase3/runtime tests/phase3/evaluation tests/phase4/registry tests/phase4/invocation tests/phase4/governance tests/phase5; do
  python3 -B -m unittest discover -s "$suite" -p 'test_*.py'
done
# The full offline command runs tests/agents in the separately hash-locked app environment.

# Docker's own parser/ignore semantics, current repository consumers and trusted baseline transport.
GOTOOLCHAIN=local go -C tools/image-inputs test -count=1 ./...
python3 -B -m unittest discover -s tools/image-inputs -p 'test_*.py'
