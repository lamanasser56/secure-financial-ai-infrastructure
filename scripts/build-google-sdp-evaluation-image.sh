#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

repository_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repository_root"

if (($# != 2)); then
  fail 'usage: build-google-sdp-evaluation-image.sh BUILDER_REF RUNTIME_REF'
fi
builder_ref=$1
runtime_ref=$2
dockerfile=docker/google-sdp-evaluation/Dockerfile
candidate_record=docker/google-sdp-evaluation/candidates.json

command -v docker >/dev/null 2>&1 || fail 'Docker is required'
command -v python3 >/dev/null 2>&1 || fail 'Python 3 is required'
command -v tar >/dev/null 2>&1 || fail 'tar is required'
docker buildx version >/dev/null 2>&1 || fail 'Docker Buildx is required'

python3 - "$candidate_record" "$dockerfile" "$builder_ref" "$runtime_ref" <<'PY' \
  || fail 'candidate record or Dockerfile is not immutable and internally consistent'
import json
from pathlib import Path
import re
import sys

record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
dockerfile = Path(sys.argv[2]).read_text(encoding="utf-8")
builder, runtime = sys.argv[3:]
ref = re.compile(r"^[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$")
if set(record) != {"schema_version", "selected", "candidates", "qualification"}:
    raise SystemExit("unknown or missing candidate-record field")
if record["schema_version"] != 1 or set(record["selected"]) != {"builder", "runtime"}:
    raise SystemExit("invalid selected candidate")
if record["selected"] != {"builder": builder, "runtime": runtime}:
    raise SystemExit("explicit base references differ from the selected candidate")
if not all(ref.fullmatch(value) and ":latest@" not in value for value in (builder, runtime)):
    raise SystemExit("mutable or floating base reference")
candidate_keys = {"source", "tag", "digest", "architecture", "compressed_size_bytes", "uncompressed_size_bytes", "high_fixable", "high_unfixable", "critical_fixable", "critical_unfixable", "result", "reason"}
if not isinstance(record["candidates"], list) or not record["candidates"]:
    raise SystemExit("missing candidate inventory")
for candidate in record["candidates"]:
    if not isinstance(candidate, dict) or set(candidate) != candidate_keys:
        raise SystemExit("unknown or missing candidate field")
    if not ref.fullmatch(candidate["tag"] + "@" + candidate["digest"]):
        raise SystemExit("candidate lacks an immutable digest")
    if candidate["architecture"] != "linux/amd64":
        raise SystemExit("unexpected candidate architecture")
known = {item["tag"] + "@" + item["digest"] for item in record["candidates"]}
if builder not in known or runtime not in known:
    raise SystemExit("selected base is missing from the inventory")
froms = re.findall(r"^FROM\s+(\S+)", dockerfile, re.MULTILINE | re.IGNORECASE)
if froms != [builder, runtime] or re.search(r"\blatest\b", dockerfile, re.IGNORECASE):
    raise SystemExit("Dockerfile bases differ or use a floating tag")
PY

content_key=$(sha256sum \
  "$dockerfile" requirements-google-sdp-runtime.txt \
  scripts/evaluate-google-sdp.py \
  runtime/phase3/__init__.py \
  runtime/phase3/google_sdp_adapter.py \
  runtime/phase3/trusted_runtime.py \
  evaluation/google-sdp/corpus.json \
  evaluation/google-sdp/corpus.schema.json \
  evaluation/google-sdp/result.schema.json \
  | sha256sum | cut -c1-16)
image_tag="portfolio-google-sdp-evaluation:local-$content_key"

temporary_directory=$(mktemp -d)
container_id=''
cleanup() {
  if [[ -n "$container_id" ]]; then
    docker rm -f "$container_id" >/dev/null 2>&1 || true
  fi
  rm -rf "$temporary_directory"
}
trap cleanup EXIT

SOURCE_DATE_EPOCH=0 DOCKER_BUILDKIT=1 docker buildx build \
  --platform linux/amd64 \
  --output "type=docker,dest=$temporary_directory/image.tar,rewrite-timestamp=true" \
  --file "$dockerfile" --tag "$image_tag" .
docker load -i "$temporary_directory/image.tar" >/dev/null

image_id=$(docker image inspect "$image_tag" --format '{{.Id}}')
image_digest=$(docker image inspect "$image_tag" --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}')
runtime_user=$(docker image inspect "$image_tag" --format '{{.Config.User}}')
[[ "$runtime_user" =~ ^[1-9][0-9]*:[1-9][0-9]*$ ]] \
  || fail 'runtime user must be a numeric non-root UID:GID'
[[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || fail 'invalid image ID'

container_id=$(docker create --network none "$image_tag")
docker export "$container_id" | tar -tf - > "$temporary_directory/files.txt"
if grep -Eq '(^|/)(\.git|\.ssh|\.aws|\.kube|\.env|gcloud)(/|$)|(^|/)(pip[0-9.]*|pytest|git|trivy|syft|cosign|gitleaks|apt(-get)?|apk|sh|bash)$' \
  "$temporary_directory/files.txt"; then
  fail 'runtime image contains a prohibited tool or credential path'
fi
docker rm "$container_id" >/dev/null
container_id=''

docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges "$image_tag" \
  > "$temporary_directory/offline.json"
python3 - "$temporary_directory/offline.json" <<'PY' \
  || fail 'offline validation did not produce a sanitized result'
import json
from pathlib import Path
import sys

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if result.get("run_mode") != "offline" or not isinstance(result.get("cases"), list):
    raise SystemExit("unexpected default execution mode")
if result.get("outcome") != "INCONCLUSIVE — MORE EVIDENCE REQUIRED":
    raise SystemExit("unexpected offline outcome")
PY

printf 'Image tag: %s\nImage ID: %s\n' "$image_tag" "$image_id"
printf 'RepoDigest: %s\nRuntime UID:GID: %s\n' "${image_digest:-unavailable}" "$runtime_user"
printf 'Offline synthetic validation: PASS (network disabled)\n'
