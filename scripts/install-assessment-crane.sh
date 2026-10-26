#!/usr/bin/env bash
set -euo pipefail

tool_dir="${1:-}"
[[ -n "$tool_dir" && "$tool_dir" == /* && -d "$tool_dir" ]] || {
  echo 'provide an existing absolute destination directory' >&2
  exit 2
}
archive="$tool_dir/go-containerregistry.tar.gz"
curl --fail --silent --show-error --location \
  --output "$archive" \
  'https://github.com/google/go-containerregistry/releases/download/v0.22.1/go-containerregistry_Linux_x86_64.tar.gz'
printf '%s  %s\n' \
  '0ab7a1d6932a213aed964ce97666c3077fe691c8606413674a8b3e0b9ec4cda0' "$archive" \
  | sha256sum --check >/dev/null
tar -xzf "$archive" -C "$tool_dir" crane
chmod 0755 "$tool_dir/crane"
"$tool_dir/crane" version >/dev/null
echo 'Pinned assessment image-copy tool verified'
