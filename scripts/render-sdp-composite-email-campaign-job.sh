#!/usr/bin/env bash
# Render a suspended context-060 email comparisons only; never apply resources.
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "$0")/.." && pwd)
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }

if [[ "$#" == 2 && "$1" == --cleanup ]]; then
  directory=$2
  [[ "$directory" =~ ^/tmp/portfolio-google-sdp-render\.[A-Za-z0-9]{8}$ ]] \
    || fail 'cleanup requires a diagnostic renderer-owned temporary directory'
  [[ -d "$directory" && ! -L "$directory" && -O "$directory" \
    && -f "$directory/.portfolio-email-render-marker" \
    && ! -L "$directory/.portfolio-email-render-marker" ]] \
    || fail 'cleanup requires a regular diagnostic ownership marker'
  [[ "$(cat "$directory/.portfolio-email-render-marker")" == portfolio-sdp-composite-email-campaign-v1 ]] \
    || fail 'unexpected diagnostic ownership marker'
  exec bash "$root/scripts/render-google-sdp-evaluation-job.sh" "$@"
fi

[[ "$#" == 3 ]] || fail 'usage: render-sdp-composite-email-campaign-job.sh PROJECT GSA EXACT_DIGEST | --cleanup DIRECTORY'
[[ "$3" =~ ^us-east1-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/sdp-evaluation-images/google-sdp-context@sha256:667ceec4b8290df1341a91a7685ad140319fca6d23f92b9948dddf9fac64136b$ ]] \
  || fail 'diagnostic profile requires its exact Artifact Registry digest'
rendered=$(bash "$root/scripts/render-google-sdp-evaluation-job.sh" "$@")
directory=$(printf '%s\n' "$rendered" | sed -n 's#^Controls: \(.*\)/google-sdp-evaluation-controls.yaml$#\1#p')
[[ "$directory" =~ ^/tmp/portfolio-google-sdp-render\.[A-Za-z0-9]{8}$ ]] \
  || fail 'unexpected inherited renderer output'
trap 'bash "$root/scripts/render-google-sdp-evaluation-job.sh" --cleanup "$directory" >/dev/null' ERR
printf 'portfolio-sdp-composite-email-campaign-v1\n' > "$directory/.portfolio-email-render-marker"
python3 - "$directory" "$root" <<'PY'
from pathlib import Path
import hashlib
import sys
import yaml

directory = Path(sys.argv[1])
# Renderer may be invoked from any working directory. Trusted source path is argv.
import importlib.util
spec = importlib.util.spec_from_file_location('composite_campaign', Path(sys.argv[2]) / 'scripts/evaluate-composite-email-campaign.py')
program = importlib.util.module_from_spec(spec); spec.loader.exec_module(program)
code = program.rendered_source(sys.argv[2])  # Exact program with the pinned module embedded.
for filename in ('google-sdp-evaluation.yaml', 'google-sdp-evaluation-controls.yaml', 'google-sdp-evaluation-job.yaml'):
    documents = list(yaml.safe_load_all((directory / filename).read_text()))
    for document in documents:
        if document['kind'] == 'ConfigMap':
            document['data']['synthetic_corpus_path'] = '/app/evaluation/google-sdp-context/corpus.json'
        if document['kind'] != 'Job':
            continue
        document['metadata']['name'] = 'google-sdp-composite-email-campaign'
        document['metadata']['annotations'] = {
            'portfolio.example/evaluation-scope': 'composite-deterministic-email-plus-provider',
            'portfolio.example/content-attempt-limit': '172',
            'portfolio.example/program-sha256': hashlib.sha256(code.encode()).hexdigest(),
        }
        document['spec']['activeDeadlineSeconds'] = 900
        container = document['spec']['template']['spec']['containers'][0]
        container['command'] = ['/usr/local/bin/python3.12']
        container['args'] = ['-c', code, '--live']
        container['env'] = [entry for entry in container['env'] if entry['name'] != 'PORTFOLIO_GOOGLE_SDP_SYNTHETIC_ONLY_ACK']
        container['env'].extend([
            {'name': 'PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK',
             'value': 'I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY'},
            {'name': 'PORTFOLIO_COMPOSITE_EMAIL_CAMPAIGN_ACK',
             'value': 'I_ACKNOWLEDGE_COMPOSITE_EMAIL_CAMPAIGN_NOT_GOOGLE_QUALIFICATION'},
        ])
    (directory / filename).write_text(yaml.safe_dump_all(documents, sort_keys=False))
PY
python3 "$root/scripts/validate-sdp-composite-email-campaign-deployment.py" "$directory/google-sdp-evaluation.yaml" >/dev/null
trap - ERR
printf 'Rendered manifest: %s/google-sdp-evaluation.yaml\n' "$directory"
printf 'Controls: %s/google-sdp-evaluation-controls.yaml\n' "$directory"
printf 'Suspended composite campaign Job: %s/google-sdp-evaluation-job.yaml\n' "$directory"
printf 'Network preflight: %s/google-sdp-egress-preflight.yaml\n' "$directory"
printf 'Dedicated-cluster logging: %s/networklogging.yaml\n' "$directory"
printf 'Identity: project=%s GSA=%s\n' "$1" "$2"
printf 'Scope: AM-R4 composite (deterministic email + unchanged Google SDP context policy on masked text); 86 frozen cases; maximum 172 content operations; zero retries; not Google qualification\n'
printf 'Cleanup: bash scripts/render-sdp-composite-email-campaign-job.sh --cleanup %s\n' "$directory"
