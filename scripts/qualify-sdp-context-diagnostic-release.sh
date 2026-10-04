#!/usr/bin/env bash
# Qualify only the committed context-001 diagnostic subject before cloud auth.
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
import hashlib
import json
import pathlib
import re
import sys

record = json.loads(pathlib.Path('evaluation/google-sdp-context/diagnostic-qualification.json').read_text())
required = {
    'schema_version': 1,
    'evaluation_profile': 'context-001-diagnostic-v1',
    'scope': 'context_001_diagnostic_only',
    'case_id': 'context-001',
    'sdk_attempt_ceiling': 2,
    'metadata_attempts': 0,
    'retries': 0,
    'job_deadline_seconds': 120,
    'max_input_bytes': 4096,
    'max_output_bytes': 4096,
    'rpc_timeout_seconds': 3,
    'redaction_deadline_seconds': 8,
    'published': False,
    'signed': False,
    'authority_changed': False,
    'google_detection_proven': False,
}
for key, expected in required.items():
    if type(record.get(key)) is not type(expected) or record[key] != expected:
        raise SystemExit('diagnostic qualification scope or limit differs')
acknowledgements = {
    'PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK': 'I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY',
    'PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK': 'I_ACKNOWLEDGE_CONTEXT_001_ONLY_TWO_ATTEMPTS',
}
if record.get('acknowledgements') != acknowledgements:
    raise SystemExit('diagnostic acknowledgement contract differs')
inputs = {
    'docker/google-sdp-context/Dockerfile',
    'docker/google-sdp-context/Dockerfile.dockerignore',
    'requirements-google-sdp-runtime.txt',
    'scripts/build-sdp-context-image.sh',
    'scripts/evaluate-sdp-context-policy.py',
    'runtime/phase3/__init__.py',
    'runtime/phase3/google_sdp_adapter.py',
    'runtime/phase3/sdp_context_policy.py',
    'runtime/phase3/trusted_runtime.py',
    'evaluation/google-sdp/deployment.json',
    'evaluation/google-sdp-context/policy.json',
    'evaluation/google-sdp-context/corpus.json',
    'evaluation/google-sdp-context/corpus.schema.json',
    'evaluation/google-sdp-context/result.schema.json',
}
hashes = record.get('source_input_sha256')
if not isinstance(hashes, dict) or set(hashes) != inputs:
    raise SystemExit('diagnostic qualification input inventory differs')
for path, expected in hashes.items():
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise SystemExit('invalid diagnostic input hash')
    if hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() != expected:
        raise SystemExit('diagnostic image input differs from qualification')
candidate = record.get('candidate', {})
if (type(candidate.get('policy_exit')) is not int or candidate['policy_exit'] != 0
        or type(candidate.get('exceptions')) is not int or candidate['exceptions'] != 0
        or candidate.get('reproducible_archives') is not True
        or candidate.get('registry_manifest_digest') is not None
        or candidate.get('signature') is not None):
    raise SystemExit('diagnostic image is not locally qualified')
archives = candidate.get('archive_sha256')
if (not isinstance(archives, list) or len(archives) != 2
        or any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in archives)
        or archives[0] != archives[1]):
    raise SystemExit('diagnostic archives are not reproducible')
vulnerabilities = candidate.get('vulnerabilities')
if not isinstance(vulnerabilities, dict):
    raise SystemExit('diagnostic vulnerability evidence is absent')
for severity in ('HIGH', 'CRITICAL'):
    count = vulnerabilities.get(severity, 0)
    if type(count) is not int or count != 0:
        raise SystemExit('diagnostic vulnerability gate failed')
configuration = candidate.get('configuration_digest')
if not isinstance(configuration, str) or not re.fullmatch('sha256:[0-9a-f]{64}', configuration):
    raise SystemExit('invalid diagnostic configuration digest')
pathlib.Path(sys.argv[1]).write_text(configuration)
pathlib.Path(sys.argv[1] + '-archive').write_text(archives[0])
PY
bash scripts/build-sdp-context-image.sh "$1" "$temporary_directory/image.tar"
[[ "$(sha256sum "$temporary_directory/image.tar" | cut -d' ' -f1)" == "$(cat "$temporary_directory/expected-config-archive")" ]]
configuration=$(python3 scripts/google-sdp-image-config-id.py "$temporary_directory/image.tar")
[[ "$configuration" == "$(cat "$temporary_directory/expected-config")" ]]
docker load -i "$temporary_directory/image.tar" > "$temporary_directory/load"
image_id=$(sed -n 's/^Loaded image ID: //p' "$temporary_directory/load")
[[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "$(docker image inspect "$image_id" --format '{{.Config.User}}')" == 65532:65532 ]]
[[ "$(docker image inspect "$image_id" --format '{{.Architecture}}')" == amd64 ]]
image_tag="portfolio-google-sdp-evaluation:local-${configuration:7:16}"
docker tag "$image_id" "$image_tag"
container_id=$(docker create --network none "$image_tag")
docker export "$container_id" | tar -tf - > "$temporary_directory/files.txt"
if grep -Eq '(^|/)(\.git|\.ssh|\.aws|\.kube|\.env|gcloud)(/|$)|(^|/)(pip[0-9.]*|pytest|git|trivy|syft|cosign|gitleaks|apt(-get)?|apk|sh|bash)$' "$temporary_directory/files.txt"; then
  printf 'diagnostic image contains a prohibited tool or credential path\n' >&2
  exit 1
fi
docker rm "$container_id" >/dev/null
container_id=''
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --cpus 0.5 --memory 512m "$image_tag" --diagnostic-first-case > "$temporary_directory/result.json"
python3 - "$temporary_directory/result.json" <<'PY'
import json
import pathlib
import sys

value = json.loads(pathlib.Path(sys.argv[1]).read_text())
# The locked image harness validates its result schema before emitting JSON.
# Publish has a fresh Python installation, so this admission uses stdlib only.
if (value.get('mode') != 'offline_reference'
        or value.get('scope') != 'context_001_diagnostic_only'
        or value.get('outcome') != 'OFFLINE_REFERENCE_PASS_GOOGLE_UNPROVEN'
        or value.get('authority_changed') is not False
        or value.get('google_quality') != 'unmeasured'
        or value.get('required_pass') != 1 or value.get('required_fail') != 0
        or value.get('observations') != 0 or value.get('unexecuted') != 0
        or value.get('sdk_attempts') != 0 or value.get('injected_attempts') != 0
        or [case.get('case_id') for case in value.get('cases', [])] != ['context-001']):
    raise SystemExit('first-case-only diagnostic offline gate failed')
PY
printf 'Image tag: %s\nImage ID: %s\nImage configuration ID: %s\n' "$image_tag" "$image_id" "$configuration"
printf 'Offline diagnostic validation: PASS (context-001 only; network disabled; Google behavior unproven)\n'
