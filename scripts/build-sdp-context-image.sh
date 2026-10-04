#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 2 ]; then
  printf 'usage: build-sdp-context-image.sh BUILDER NEW_ABSOLUTE_ARCHIVE\n' >&2
  exit 2
fi
builder=$1
archive=$2
[[ "$builder" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]]
[[ "$archive" = /* && "$archive" = *.tar && ! -e "$archive" && ! -L "$archive" ]]
docker buildx inspect "$builder" --bootstrap | awk '
  /^Driver:/ { if ($2 != "docker-container") exit 1; found=1 }
  END { if (!found) exit 1 }
'
repository_root=$(cd "$(dirname "$0")/.." && pwd)
docker buildx build --builder "$builder" --platform linux/amd64 \
  --provenance=false --sbom=false --build-arg SOURCE_DATE_EPOCH=0 \
  --file "$repository_root/docker/google-sdp-context/Dockerfile" \
  --output "type=docker,dest=$archive,rewrite-timestamp=true" "$repository_root"
