#!/usr/bin/env bash
# Render a suspended context-001 diagnostic only; never apply resources.
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "$0")/.." && pwd)
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }

if [[ "$#" == 2 && "$1" == --cleanup ]]; then
  directory=$2
  [[ "$directory" =~ ^/tmp/portfolio-google-sdp-render\.[A-Za-z0-9]{8}$ ]] \
    || fail 'cleanup requires a diagnostic renderer-owned temporary directory'
  [[ -d "$directory" && ! -L "$directory" && -O "$directory" \
    && -f "$directory/.portfolio-diagnostic-render-marker" \
    && ! -L "$directory/.portfolio-diagnostic-render-marker" ]] \
    || fail 'cleanup requires a regular diagnostic ownership marker'
  [[ "$(cat "$directory/.portfolio-diagnostic-render-marker")" == portfolio-sdp-context-diagnostic-v1 ]] \
    || fail 'unexpected diagnostic ownership marker'
  exec bash "$root/scripts/render-google-sdp-evaluation-job.sh" "$@"
fi

[[ "$#" == 3 ]] || fail 'usage: render-sdp-context-diagnostic-job.sh PROJECT GSA EXACT_DIGEST | --cleanup DIRECTORY'
[[ "$3" =~ ^us-east1-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/sdp-evaluation-images/google-sdp-context-diagnostic@sha256:[0-9a-f]{64}$ ]] \
  || fail 'diagnostic profile requires its exact Artifact Registry digest'
rendered=$(bash "$root/scripts/render-google-sdp-evaluation-job.sh" "$@")
directory=$(printf '%s\n' "$rendered" | sed -n 's#^Controls: \(.*\)/google-sdp-evaluation-controls.yaml$#\1#p')
[[ "$directory" =~ ^/tmp/portfolio-google-sdp-render\.[A-Za-z0-9]{8}$ ]] \
  || fail 'unexpected inherited renderer output'
trap 'bash "$root/scripts/render-google-sdp-evaluation-job.sh" --cleanup "$directory" >/dev/null' ERR
printf 'portfolio-sdp-context-diagnostic-v1\n' > "$directory/.portfolio-diagnostic-render-marker"
python3 - "$directory" <<'PY'
from pathlib import Path
import sys
import yaml

directory = Path(sys.argv[1])
for filename in ('google-sdp-evaluation.yaml', 'google-sdp-evaluation-controls.yaml', 'google-sdp-evaluation-job.yaml'):
    documents = list(yaml.safe_load_all((directory / filename).read_text()))
    for document in documents:
        if document['kind'] == 'ConfigMap':
            document['data']['synthetic_corpus_path'] = '/app/evaluation/google-sdp-context/corpus.json'
        if document['kind'] != 'Job':
            continue
        document['metadata']['name'] = 'google-sdp-context-diagnostic'
        document['metadata']['annotations'] = {
            'portfolio.example/evaluation-scope': 'context-001-only',
            'portfolio.example/content-attempt-limit': '2',
        }
        document['spec']['activeDeadlineSeconds'] = 120
        container = document['spec']['template']['spec']['containers'][0]
        container['args'] = ['--live', '--diagnostic-first-case']
        container['env'] = [entry for entry in container['env'] if entry['name'] != 'PORTFOLIO_GOOGLE_SDP_SYNTHETIC_ONLY_ACK']
        container['env'].extend([
            {'name': 'PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK',
             'value': 'I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY'},
            {'name': 'PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK',
             'value': 'I_ACKNOWLEDGE_CONTEXT_001_ONLY_TWO_ATTEMPTS'},
        ])
    (directory / filename).write_text(yaml.safe_dump_all(documents, sort_keys=False))
PY
python3 "$root/scripts/validate-sdp-context-diagnostic-deployment.py" "$directory/google-sdp-evaluation.yaml" >/dev/null
trap - ERR
printf 'Rendered manifest: %s/google-sdp-evaluation.yaml\n' "$directory"
printf 'Controls: %s/google-sdp-evaluation-controls.yaml\n' "$directory"
printf 'Suspended diagnostic Job: %s/google-sdp-evaluation-job.yaml\n' "$directory"
printf 'Network preflight: %s/google-sdp-egress-preflight.yaml\n' "$directory"
printf 'Dedicated-cluster logging: %s/networklogging.yaml\n' "$directory"
printf 'Identity: project=%s GSA=%s\n' "$1" "$2"
printf 'Scope: context-001 only; maximum two attempted content operations; zero retries\n'
printf 'Cleanup: bash scripts/render-sdp-context-diagnostic-job.sh --cleanup %s\n' "$directory"
