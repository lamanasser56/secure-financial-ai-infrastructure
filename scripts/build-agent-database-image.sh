#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
[[ $# == 3 ]]
builder=$1
archive=$2
epoch=$3
[[ "$builder" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]]
[[ "$archive" == /*.tar && ! -e "$archive" && ! -L "$archive" ]]
[[ "$epoch" =~ ^[0-9]{1,12}$ ]]
root=$(cd "$(dirname "$0")/.." && pwd)
docker buildx inspect "$builder" --bootstrap | awk '
  /^Driver:/ { if ($2 != "docker-container") exit 1; found=1 }
  END { if (!found) exit 1 }
'
docker buildx build --builder "$builder" --platform linux/amd64 \
  --provenance=false --sbom=false --build-arg "SOURCE_DATE_EPOCH=$epoch" \
  --tag portfolio-agent-database:qualified \
  --file "$root/docker/agent-database/Dockerfile" \
  --output "type=docker,dest=$archive,rewrite-timestamp=true" "$root"
