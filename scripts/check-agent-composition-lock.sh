#!/usr/bin/env bash
set -Eeuo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
python3 -c 'import sys; from importlib.metadata import version; assert sys.version_info[:2] == (3, 12); assert version("pip-tools") == "7.6.1"'
lock_directory=$(mktemp -d)
trap 'rm -rf "$lock_directory"' EXIT
cp requirements-agent-composition.in requirements-agent-composition.txt requirements-litellm-candidate.txt "$lock_directory/"
(
  cd "$lock_directory"
  PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=0 PIP_EXTRA_INDEX_URL='' PIP_FIND_LINKS='' \
    PIP_INDEX_URL=https://pypi.org/simple python3 -m piptools compile \
      --quiet --generate-hashes --resolver=backtracking --allow-unsafe \
      --strip-extras --index-url https://pypi.org/simple \
      --output-file requirements-agent-composition.txt requirements-agent-composition.in
)
cmp -s requirements-agent-composition.txt "$lock_directory/requirements-agent-composition.txt" \
  || { echo 'FAIL: stale composition dependency lock' >&2; exit 1; }
echo 'PASS: composition dependency lock'
