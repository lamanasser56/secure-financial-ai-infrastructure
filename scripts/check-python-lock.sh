#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repository_root"

python3 -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 is required"'
python3 -c 'from importlib.metadata import version; assert version("pip-tools") == "7.6.1", "pip-tools 7.6.1 is required"'

temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT
cp requirements-dev.in requirements-dev.txt "$temporary_directory/"

(
  cd "$temporary_directory"
  PIP_CONFIG_FILE=/dev/null \
    PIP_NO_INDEX=0 \
    PIP_EXTRA_INDEX_URL='' \
    PIP_FIND_LINKS='' \
    PIP_INDEX_URL=https://pypi.org/simple \
    python3 -m piptools compile \
      --quiet \
      --generate-hashes \
      --resolver=backtracking \
      --allow-unsafe \
      --strip-extras \
      --index-url https://pypi.org/simple \
      --output-file requirements-dev.txt \
      requirements-dev.in
)

if ! cmp -s requirements-dev.txt "$temporary_directory/requirements-dev.txt"; then
  echo 'requirements-dev.txt is stale; regenerate it with Python 3.12 and pip-tools 7.6.1.' >&2
  diff -u requirements-dev.txt "$temporary_directory/requirements-dev.txt" || true
  exit 1
fi
echo 'Python dependency lock is current.'
