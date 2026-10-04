#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -c 'import sys; assert sys.version_info[:2] == (3, 12)'
python3 -c 'from importlib.metadata import version; assert version("pip-tools") == "7.6.1"'
lock_directory=$(mktemp -d)
trap 'rm -rf "$lock_directory"' EXIT
cp requirements-presidio-runtime.in requirements-presidio-runtime.txt "$lock_directory/"
(
  cd "$lock_directory"
  PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=0 PIP_EXTRA_INDEX_URL='' \
    PIP_FIND_LINKS='' PIP_INDEX_URL=https://pypi.org/simple \
    python3 -m piptools compile --quiet --generate-hashes --resolver=backtracking \
      --allow-unsafe --strip-extras --index-url https://pypi.org/simple \
      --output-file requirements-presidio-runtime.txt requirements-presidio-runtime.in
)
if ! cmp -s requirements-presidio-runtime.txt "$lock_directory/requirements-presidio-runtime.txt"; then
  echo 'Presidio candidate lock is stale.' >&2
  exit 1
fi
echo 'Presidio candidate dependency lock is current.'
