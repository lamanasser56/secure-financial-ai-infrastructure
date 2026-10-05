#!/usr/bin/env bash
# Qualify only the committed frozen full context campaign subject before cloud auth.
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

record = json.loads(pathlib.Path('evaluation/google-sdp-context/campaign-qualification.json').read_text())
required = {
    'schema_version': 1,
    'evaluation_profile': 'context-pattern-v1',
    'scope': 'context_pattern_v1_campaign',
    'required_cases': 70,
    'observation_cases': 16,
    'sdk_attempt_ceiling': 172,
    'metadata_attempts': 0,
    'retries': 0,
    'job_deadline_seconds': 900,
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
        raise SystemExit('campaign qualification scope or limit differs')
acknowledgements = {
    'PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK': 'I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY',
}
if record.get('acknowledgements') != acknowledgements:
    raise SystemExit('campaign acknowledgement contract differs')
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
    raise SystemExit('campaign qualification input inventory differs')
for path, expected in hashes.items():
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise SystemExit('invalid campaign input hash')
    if hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() != expected:
        raise SystemExit('campaign image input differs from qualification')
if (record.get('policy_sha256') != 'c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db'
        or record.get('corpus_sha256') != '0c07aa1e8b480e732cdcaa6e9f406661058220ad41de607af7124198e5e71eb9'
        or hashes['evaluation/google-sdp-context/policy.json'] != record['policy_sha256']
        or hashes['evaluation/google-sdp-context/corpus.json'] != record['corpus_sha256']):
    raise SystemExit('campaign frozen policy or corpus differs')
candidate = record.get('candidate', {})
if (type(candidate.get('sbom_components')) is not int or candidate['sbom_components'] < 1
        or candidate.get('secret_scanning', {}).get('image_filesystem_findings') != 0
        or candidate.get('secret_scanning', {}).get('version') != '8.30.1'):
    raise SystemExit('campaign SBOM or secret evidence is absent')
if (type(candidate.get('policy_exit')) is not int or candidate['policy_exit'] != 0
        or type(candidate.get('exceptions')) is not int or candidate['exceptions'] != 0
        or candidate.get('reproducible_archives') is not True
        or candidate.get('registry_manifest_digest') is not None
        or candidate.get('signature') is not None):
    raise SystemExit('campaign image is not locally qualified')
archives = candidate.get('archive_sha256')
if (not isinstance(archives, list) or len(archives) != 2
        or any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in archives)
        or archives[0] != archives[1]):
    raise SystemExit('campaign archives are not reproducible')
vulnerabilities = candidate.get('vulnerabilities')
if not isinstance(vulnerabilities, dict):
    raise SystemExit('campaign vulnerability evidence is absent')
for severity in ('HIGH', 'CRITICAL'):
    count = vulnerabilities.get(severity, 0)
    if type(count) is not int or count != 0:
        raise SystemExit('campaign vulnerability gate failed')
configuration = candidate.get('configuration_digest')
if not isinstance(configuration, str) or not re.fullmatch('sha256:[0-9a-f]{64}', configuration):
    raise SystemExit('invalid campaign configuration digest')
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
  printf 'campaign image contains a prohibited tool or credential path\n' >&2
  exit 1
fi
docker rm "$container_id" >/dev/null
container_id=''
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --cpus 0.5 --memory 512m "$image_tag" > "$temporary_directory/result.json"
python3 - "$temporary_directory/result.json" <<'PY'
import json
import pathlib
import sys

value = json.loads(pathlib.Path(sys.argv[1]).read_text())
# The locked image harness validates its result schema before emitting JSON.
# Publish has a fresh Python installation, so this admission uses stdlib only.
if (value.get('mode') != 'offline_reference'
        or value.get('scope') != 'context_pattern_v1_campaign'
        or value.get('outcome') != 'OFFLINE_REFERENCE_PASS_GOOGLE_UNPROVEN'
        or value.get('authority_changed') is not False
        or value.get('google_quality') != 'unmeasured'
        or value.get('required_pass') != 70 or value.get('required_fail') != 0
        or value.get('observations') != 16 or value.get('unexecuted') != 0
        or value.get('operational_failures') != 0 or value.get('observation_failures') != 0
        or value.get('sdk_attempts') != 0 or value.get('injected_attempts') != 0
        or [case.get('case_id') for case in value.get('cases', [])] != [f'context-{index:03}' for index in range(1, 87)]):
    raise SystemExit('full campaign offline gate failed')
PY
printf 'Image tag: %s\nImage ID: %s\nImage configuration ID: %s\n' "$image_tag" "$image_id" "$configuration"
printf 'Offline campaign validation: PASS (70 mandatory + 16 unsupported observations; network disabled; Google behavior unproven)\n'
