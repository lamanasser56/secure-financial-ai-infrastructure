#!/usr/bin/env bash
# Build only exact locally prepared subjects; no registry/cloud authentication.
set -Eeuo pipefail
umask 077
[[ $# == 4 ]]
builder=$1
target=$2
archive=$3
epoch=$4
[[ "$builder" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]]
[[ "$target" == gateway || "$target" == application ]]
[[ "$archive" == /*.tar && ! -e "$archive" && ! -L "$archive" ]]
[[ "$epoch" =~ ^[0-9]{1,12}$ ]]
root=$(cd "$(dirname "$0")/.." && pwd)
python3 "$root/scripts/verify-agent-composition-build-inputs.py"
docker buildx inspect "$builder" --bootstrap | awk '
  /^Driver:/ { if ($2 != "docker-container") exit 1; found=1 }
  END { if (!found) exit 1 }
'
docker buildx build --builder "$builder" --platform linux/amd64 \
  --provenance=false --sbom=false --build-arg "SOURCE_DATE_EPOCH=$epoch" \
  --tag "portfolio-agent-$target:qualified" \
  --target "$target" --file "$root/docker/agent-composition/Dockerfile" \
  --output "type=docker,dest=$archive,rewrite-timestamp=true" "$root"
