#!/usr/bin/env bash
# Render only. Existing identity/network/security controls are reused unchanged.
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "$0")/.." && pwd)
if [[ "$#" == 2 && "$1" == --cleanup ]]; then
  exec bash "$root/scripts/render-google-sdp-evaluation-job.sh" "$@"
fi
[[ "$#" == 3 ]] || { printf 'usage: render-sdp-context-job.sh PROJECT GSA EXACT_DIGEST\n' >&2; exit 2; }
[[ "$3" =~ ^us-east1-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/sdp-evaluation-images/google-sdp-context@sha256:[0-9a-f]{64}$ ]] \
  || { printf 'context profile requires its exact Artifact Registry digest\n' >&2; exit 2; }
rendered=$(bash "$root/scripts/render-google-sdp-evaluation-job.sh" "$@")
directory=$(printf '%s\n' "$rendered" | sed -n 's#^Controls: \(.*\)/google-sdp-evaluation-controls.yaml$#\1#p')
[[ "$directory" =~ ^/tmp/portfolio-google-sdp-render\.[A-Za-z0-9]{8}$ ]]
trap 'bash "$root/scripts/render-google-sdp-evaluation-job.sh" --cleanup "$directory" >/dev/null' ERR
python3 - "$directory" <<'PY'
from pathlib import Path
import sys, yaml
d = Path(sys.argv[1])
for filename in ('google-sdp-evaluation.yaml', 'google-sdp-evaluation-controls.yaml', 'google-sdp-evaluation-job.yaml'):
    documents = list(yaml.safe_load_all((d / filename).read_text()))
    for job in documents:
        if job['kind'] == 'ConfigMap':
            job['data']['synthetic_corpus_path'] = '/app/evaluation/google-sdp-context/corpus.json'
        if job['kind'] != 'Job':
            continue
        job['metadata']['name'] = 'google-sdp-context-evaluation'
        job['spec']['activeDeadlineSeconds'] = 900
        container = job['spec']['template']['spec']['containers'][0]
        container['args'] = ['--live']
        container['env'] = [e for e in container['env'] if e['name'] != 'PORTFOLIO_GOOGLE_SDP_SYNTHETIC_ONLY_ACK']
        container['env'].append({'name': 'PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK',
                                'value': 'I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY'})
    (d / filename).write_text(yaml.safe_dump_all(documents, sort_keys=False))
PY
python3 "$root/scripts/validate-sdp-context-job.py" "$directory/google-sdp-evaluation.yaml" >/dev/null
trap - ERR
printf '%s\n' "$rendered"
