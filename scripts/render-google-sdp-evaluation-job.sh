#!/usr/bin/env bash
set -Eeuo pipefail

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }
root=$(cd "$(dirname "$0")/.." && pwd)

if (($# == 2)) && [[ "$1" == --cleanup ]]; then
  directory=$2
  [[ "$directory" =~ ^/tmp/portfolio-google-sdp-render\.[A-Za-z0-9]{8}$ && -f "$directory/.portfolio-render-marker" ]] \
    || fail 'cleanup requires a renderer-owned temporary directory'
  rm -rf -- "$directory"
  printf 'Removed rendered evaluation directory\n'
  exit 0
fi

if (($# != 3)); then
  fail 'usage: render-google-sdp-evaluation-job.sh PROJECT_ID GSA_EMAIL ARTIFACT_REGISTRY_DIGEST | --cleanup DIRECTORY'
fi
project=$1
gsa=$2
image=$3
[[ "$project" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || fail 'invalid project ID'
[[ "$gsa" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com$ ]] \
  || fail 'invalid GSA email'
[[ "$gsa" == *"@$project.iam.gserviceaccount.com" ]] || fail 'GSA must belong to the supplied project'
[[ "$image" =~ ^me-central2-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/[a-z][a-z0-9-]{0,62}/[a-z][a-z0-9._-]{0,127}@sha256:[0-9a-f]{64}$ ]] \
  || fail 'image must be a me-central2 Artifact Registry sha256 digest'
[[ "$image" == "me-central2-docker.pkg.dev/$project/"* ]] || fail 'image project must match trusted project ID'

command -v python3 >/dev/null || fail 'Python 3 is required'
python3 -c 'import yaml' >/dev/null || fail 'PyYAML is required'
directory=$(mktemp -d /tmp/portfolio-google-sdp-render.XXXXXXXX)
trap 'rm -rf -- "$directory"' ERR
printf 'portfolio-google-sdp-render-v1\n' > "$directory/.portfolio-render-marker"
python3 - "$root/kubernetes/apps/google-sdp-evaluation" "$directory" "$project" "$gsa" "$image" <<'PY'
from pathlib import Path
import sys
import yaml

source, target = map(Path, sys.argv[1:3])
project, gsa, image = sys.argv[3:]
substitutions = {
    "REPLACE_WITH_PROJECT_ID": project,
    "REPLACE_WITH_GSA_EMAIL": gsa,
    "REPLACE_WITH_ARTIFACT_REGISTRY_DIGEST": image,
}
resources = yaml.safe_load((source / "kustomization.yaml").read_text())["resources"]
documents = []
for filename in resources:
    if filename != Path(filename).name or not filename.endswith(".yaml"):
        raise SystemExit("invalid Kustomize resource path")
    content = (source / filename).read_text(encoding="utf-8")
    for placeholder, value in substitutions.items():
        content = content.replace(placeholder, value)
    if "REPLACE_WITH_" in content:
        raise SystemExit("unfilled deployment placeholder")
    documents.append(yaml.safe_load(content))
output = target / "google-sdp-evaluation.yaml"
output.write_text(yaml.safe_dump_all(documents, sort_keys=False), encoding="utf-8")
PY
bash "$root/scripts/validate-google-sdp-deployment.sh" "$directory/google-sdp-evaluation.yaml" >/dev/null
trap - ERR
printf 'Rendered manifest: %s/google-sdp-evaluation.yaml\n' "$directory"
printf 'Identity: project=%s GSA=%s\n' "$project" "$gsa"
printf 'Cleanup: bash scripts/render-google-sdp-evaluation-job.sh --cleanup %s\n' "$directory"
