#!/usr/bin/env bash
# One fail-closed, repo-owned offline suite: CI and make test call this same command.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

need() { command -v "$1" >/dev/null 2>&1 || { echo "offline prerequisite missing: $1" >&2; exit 2; }; }
for tool in python3 go node npm git make; do need "$tool"; done
python3 -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 required"'
export PYTHONDONTWRITEBYTECODE=1
python3 -B scripts/install-platform-tools.py
export PATH="$PWD/.cache/platform-tools:$PWD/.cache/envtest-v1.35.0:$PATH"

venv="$PWD/.cache/offline-app-venv"
dev_venv="$PWD/.cache/offline-dev-venv"
eval_venv="$PWD/.cache/offline-eval-venv"
for path in "$venv" "$dev_venv" "$eval_venv"; do
  if [[ ! -x "$path/bin/python" ]]; then python3 -m venv "$path"; fi
done
"$venv/bin/python" -m pip install --disable-pip-version-check --require-hashes \
  -r requirements-litellm-candidate.txt -r requirements-agent-composition.txt \
  -r requirements-financial-agent.txt
"$dev_venv/bin/python" -m pip install --disable-pip-version-check --require-hashes \
  -r requirements-dev.txt
"$eval_venv/bin/python" -m pip install --disable-pip-version-check --require-hashes \
  -r requirements-google-sdp.txt
export PATH="$venv/bin:$PATH"

if [[ -z "${FINANCE_TEST_DSN:-}" ]]; then
  need docker
  if docker info >/dev/null 2>&1; then
    docker_cmd=(docker)
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    docker_cmd=(sudo -n docker)
  else
    echo 'offline Docker daemon unavailable' >&2; exit 2
  fi
  name="sfai-offline-postgres-$$"
  "${docker_cmd[@]}" run --detach --rm --name "$name" \
    -e POSTGRES_PASSWORD=ci-only-not-a-secret -p 127.0.0.1::5432 \
    postgres:17.6-bookworm@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3 >/dev/null
  trap '"${docker_cmd[@]}" rm --force "$name" >/dev/null 2>&1 || true' EXIT
  port=$("${docker_cmd[@]}" port "$name" 5432/tcp | awk -F: 'NR==1 {print $NF}')
  [[ "$port" =~ ^[0-9]+$ ]] || { echo 'offline Postgres port unavailable' >&2; exit 2; }
  export FINANCE_TEST_DSN="postgresql://postgres:ci-only-not-a-secret@127.0.0.1:$port/postgres"
  ready=0
  for _ in {1..40}; do
    if "${docker_cmd[@]}" exec "$name" pg_isready -U postgres >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  ((ready)) || { echo 'offline Postgres did not become ready' >&2; exit 2; }
fi

PATH="$dev_venv/bin:$PATH" bash scripts/check.sh
PYTHONPATH=platform/core/src:platform/agents/financial:. \
  python -B -m unittest discover -s tests/agents -p 'test_*.py'
make test-policies PYTHON="$venv/bin/python"
PYTHONPATH=platform/core/src:platform/core/tests:platform/agents/financial:. \
  python -B -m unittest discover -s platform/core/tests -p 'test_*.py'
PYTHONPATH=platform/core/src:. python -B -m agent_platform.providers check gemini
PYTHONPATH=platform/core/src:. python -B -m agent_platform.onboarding check
PYTHONPATH=assessment_overlay:platform/core/src/agent_platform/programs:platform/core/src:. \
  python -B -m unittest discover -s assessment_overlay -p test_followup.py
PYTHONPATH=assessment_overlay:platform/core/src:. \
  python -B -m unittest discover -s assessment_overlay -p 'test_live_*.py'
PYTHONPATH=platform/core/src:platform/agents/financial:. \
  python -B -m unittest discover -s platform/agents/financial/tests -p 'test_*.py'
node --test platform/agents/platform-guide/test/*.test.js
"$eval_venv/bin/python" -B scripts/evaluate-google-sdp.py >/dev/null
terraform -chdir=platform/clouds/gke/terraform/root init -backend=false -input=false -lockfile=readonly >/dev/null
terraform -chdir=platform/clouds/gke/terraform/root validate -no-color
terraform fmt -check -recursive platform/clouds/gke/terraform
PATH="$dev_venv/bin:$PATH" bash scripts/lint-repository.sh
npm ci --prefix tests/browser --ignore-scripts
tests/browser/node_modules/.bin/playwright install --with-deps chromium
npm --prefix tests/browser test
echo 'full offline suite passed'
