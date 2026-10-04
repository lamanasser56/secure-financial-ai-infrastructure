#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 3 ]; then
  printf 'usage: build-litellm-candidate.sh BUILDER ARCHIVE SOURCE_EPOCH\n' >&2
  exit 2
fi
builder=$1
archive=$2
source_epoch=$3
[[ "$builder" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]]
[[ "$archive" = /* && "$archive" = *.tar && ! -e "$archive" && ! -L "$archive" ]]
[[ "$source_epoch" =~ ^[0-9]{1,12}$ ]]
docker buildx inspect "$builder" --bootstrap | awk '
  /^Driver:/ { if ($2 != "docker-container") exit 1; found=1 }
  END { if (!found) exit 1 }
'
repository_root=$(cd "$(dirname "$0")/.." && pwd)
docker buildx build --builder "$builder" --platform linux/amd64 \
  --provenance=false --sbom=false --build-arg "SOURCE_DATE_EPOCH=$source_epoch" \
  --file "$repository_root/docker/litellm-candidate/Dockerfile" \
  --output "type=docker,dest=$archive,rewrite-timestamp=true" "$repository_root"
