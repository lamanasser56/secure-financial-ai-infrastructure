#!/usr/bin/env bash
# Called by the existing release build seam, before cloud authentication.
set -Eeuo pipefail
umask 077
[[ "$#" == 1 ]]
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
temporary_directory=$(mktemp -d)
container_id=''
cleanup() {
  if [[ -n "$container_id" ]]; then
    docker rm -f "$container_id" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$temporary_directory"
}
trap cleanup EXIT
python3 - "$temporary_directory/expected-config" <<'PY'
import hashlib, json, pathlib, sys
record = json.loads(pathlib.Path('evaluation/google-sdp-context/qualification.json').read_text())
if record['candidate']['policy_exit'] != 0 or record['candidate']['exceptions'] != 0:
    raise SystemExit('context image is not qualified')
for path, expected in record['source_input_sha256'].items():
    if hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() != expected:
        raise SystemExit('context image input differs from qualification')
pathlib.Path(sys.argv[1]).write_text(record['candidate']['configuration_digest'])
PY
bash scripts/build-sdp-context-image.sh "$1" "$temporary_directory/image.tar"
configuration=$(python3 scripts/google-sdp-image-config-id.py "$temporary_directory/image.tar")
[[ "$configuration" == "$(cat "$temporary_directory/expected-config")" ]]
docker load -i "$temporary_directory/image.tar" > "$temporary_directory/load"
image_id=$(sed -n 's/^Loaded image ID: //p' "$temporary_directory/load")
[[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "$(docker image inspect "$image_id" --format '{{.Config.User}}')" == 65532:65532 ]]
image_tag="portfolio-google-sdp-evaluation:local-${configuration:7:16}"
docker tag "$image_id" "$image_tag"
container_id=$(docker create --network none "$image_tag")
docker export "$container_id" | tar -tf - > "$temporary_directory/files.txt"
if grep -Eq '(^|/)(\.git|\.ssh|\.aws|\.kube|\.env|gcloud)(/|$)|(^|/)(pip[0-9.]*|pytest|git|trivy|syft|cosign|gitleaks|apt(-get)?|apk|sh|bash)$' "$temporary_directory/files.txt"; then
  printf 'context image contains a prohibited tool or credential path\n' >&2
  exit 1
fi
docker rm "$container_id" >/dev/null
container_id=''
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --cpus 0.5 --memory 512m "$image_tag" > "$temporary_directory/result.json"
python3 - "$temporary_directory/result.json" <<'PY'
import json, sys
v = json.load(open(sys.argv[1]))
if (v['mode'] != 'offline_reference' or v['required_pass'] != 70 or v['observations'] != 16
    or v['sdk_attempts'] != 0 or v['required_fail'] != 0 or v['unexecuted'] != 0):
    raise SystemExit('context offline gate failed')
PY
printf 'Image tag: %s\nImage ID: %s\nImage configuration ID: %s\n' "$image_tag" "$image_id" "$configuration"
printf 'Offline synthetic validation: PASS (network disabled; Google behavior unproven)\n'
