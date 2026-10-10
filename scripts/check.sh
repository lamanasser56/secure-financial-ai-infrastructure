#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
bash scripts/check-python-lock.sh
bash scripts/check-presidio-runtime-lock.sh
if [ "${PORTFOLIO_CHECK_GOOGLE_SDP_LOCK:-0}" = 1 ]; then
  bash scripts/check-google-sdp-lock.sh
  bash scripts/check-google-sdp-runtime-lock.sh
fi
if [ "${PORTFOLIO_CHECK_AGENT_PREPARATION_LOCKS:-0}" = 1 ]; then
  bash scripts/check-agent-preparation-locks.sh
fi
if [ "${PORTFOLIO_CHECK_AGENT_COMPOSITION_LOCK:-0}" = 1 ]; then
  bash scripts/check-agent-composition-lock.sh
fi
python3 -B scripts/validate.py
python3 -B scripts/check-references.py
bash scripts/validate-google-sdp-deployment.sh
bash scripts/validate-google-sdp-gcp-bootstrap.sh
python3 -B scripts/validate-google-sdp-execution.py
for suite in tests/phase3/runtime tests/phase3/evaluation tests/phase4/registry tests/phase4/invocation tests/phase4/governance tests/phase5; do
  python3 -B -m unittest discover -s "$suite" -p 'test_*.py'
done
# tests/agents needs the application's runtime dependency set (the app image locks); the CI `agents` job installs
# it and runs this suite together with platform/core tests and the real-API-server policy tests.
if python3 -c 'import cryptography, google.auth, psycopg' 2>/dev/null; then
  python3 -B -m unittest discover -s tests/agents -p 'test_*.py'
else
  echo 'tests/agents: runtime dependencies absent here; run in the agents CI job (or install the app image locks).'
fi
