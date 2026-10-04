#!/usr/bin/env bash
set -euo pipefail
repository_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repository_root"
python3 -c 'import sys; from importlib.metadata import version; assert sys.version_info[:2] == (3, 12); assert version("pip-tools") == "7.6.1"'
temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT
for lock in requirements-agent-identity requirements-litellm-candidate; do
  relative_prefix=''
  if [ "$lock" = requirements-litellm-candidate ]; then
    # Preserve the committed compiler's relative source paths in its header.
    relative_prefix='source/'
    mkdir -p "$temporary_directory/source"
  fi
  cp "$lock.in" "$lock.txt" "$temporary_directory/$relative_prefix"
  (
    cd "$temporary_directory"
    PIP_CONFIG_FILE=/dev/null PIP_EXTRA_INDEX_URL='' PIP_FIND_LINKS='' \
      PIP_INDEX_URL=https://pypi.org/simple python3 -m piptools compile \
      --quiet --generate-hashes --resolver=backtracking --allow-unsafe \
      --strip-extras --index-url https://pypi.org/simple \
      --output-file "$relative_prefix$lock.txt" "$relative_prefix$lock.in"
  )
  cmp -s "$lock.txt" "$temporary_directory/$relative_prefix$lock.txt" \
    || { printf 'FAIL: stale candidate lock %s\n' "$lock" >&2; exit 1; }
  printf 'PASS: %s lock\n' "$lock"
done
