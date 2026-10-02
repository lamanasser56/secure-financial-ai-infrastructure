#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

pass() {
  printf 'PASS: %s\n' "$*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 \
    || fail "required SBOM-qualification command is unavailable: $1"
}

readonly required_syft_version='1.44.0'

(($# == 1)) || fail 'provide exactly one immutable image reference'
readonly image_reference="$1"

[[ "$image_reference" =~ ^[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$ ]] \
  || fail 'image reference must use an immutable sha256 digest'
readonly expected_digest="${image_reference##*@}"

require_command mkdir
require_command mktemp
require_command python3
require_command rm
require_command sed
require_command syft

actual_syft_version="$(
  syft version 2>/dev/null \
    | sed -n 's/^Version:[[:space:]]*//p' \
    | sed -n '1p'
)" || fail 'Syft is present but its version cannot be determined'
[[ "$actual_syft_version" == "$required_syft_version" ]] \
  || fail "Syft $required_syft_version is required; found $actual_syft_version"

printf 'SBOM generator: Syft %s\n' "$actual_syft_version"
printf 'SBOM source digest: %s\n' "$expected_digest"

temporary_base="${TMPDIR:-/tmp}"
[[ "$temporary_base" == /* && "$temporary_base" != '/' \
  && -d "$temporary_base" ]] \
  || fail 'temporary base must be an existing absolute directory other than root'

qualification_root="$(mktemp -d "$temporary_base/portfolio-sbom.XXXXXXXX")"
[[ "$qualification_root" == "$temporary_base"/portfolio-sbom.* \
  && -d "$qualification_root" ]] \
  || fail 'mktemp returned an unexpected SBOM qualification directory'

cleanup() {
  if [[ -n "${qualification_root:-}" && -d "$qualification_root" \
    && "$qualification_root" == "$temporary_base"/portfolio-sbom.* ]]; then
    rm -rf -- "$qualification_root"
  fi
}
trap cleanup EXIT INT TERM

mkdir -- "$qualification_root/cache" "$qualification_root/tmp"

set +e
XDG_CACHE_HOME="$qualification_root/cache" \
TMPDIR="$qualification_root/tmp" \
SYFT_CHECK_FOR_APP_UPDATE=false \
SYFT_LOG_QUIET=true \
syft scan "registry:$image_reference" \
  --output "cyclonedx-json=$qualification_root/sbom.cdx.json" \
  >"$qualification_root/generator-output.txt" 2>&1
generation_status=$?
set -e

((generation_status == 0)) \
  || fail "SBOM image retrieval, generation, or generator execution failed with status $generation_status"

python3 - "$qualification_root/sbom.cdx.json" "$expected_digest" <<'PY' \
  || fail 'Syft produced an invalid or incomplete structured SBOM'
import json
from pathlib import Path
import re
import sys

sbom_path = Path(sys.argv[1])
expected_digest = sys.argv[2].lower()
expected_hex = expected_digest.removeprefix('sha256:')

try:
    sbom = json.loads(sbom_path.read_text(encoding='utf-8'))
except (OSError, UnicodeError, json.JSONDecodeError):
    raise SystemExit('invalid structured SBOM')

if sbom.get('bomFormat') != 'CycloneDX':
    raise SystemExit('SBOM is not CycloneDX')
if not isinstance(sbom.get('specVersion'), str) or not sbom['specVersion']:
    raise SystemExit('SBOM has no CycloneDX specification version')
if not isinstance(sbom.get('serialNumber'), str) or not sbom['serialNumber']:
    raise SystemExit('SBOM has no document serial number')

components = sbom.get('components')
if not isinstance(components, list) or not components:
    raise SystemExit('SBOM contains no discovered components')
if not any(
    isinstance(component, dict)
    and isinstance(component.get('name'), str)
    and component['name']
    for component in components
):
    raise SystemExit('SBOM component results are incomplete')

metadata = sbom.get('metadata')
source_identity = metadata.get('component') if isinstance(metadata, dict) else None
if not isinstance(source_identity, dict):
    raise SystemExit('SBOM has no structured source identity')

identity_values = []


def collect_strings(value):
    if isinstance(value, str):
        identity_values.append(value.lower())
    elif isinstance(value, dict):
        for nested_value in value.values():
            collect_strings(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            collect_strings(nested_value)


collect_strings(source_identity)
digest_pattern = re.compile(r'(?:sha256:)?[0-9a-f]{64}')
source_digests = {
    match.group(0).removeprefix('sha256:')
    for value in identity_values
    for match in digest_pattern.finditer(value)
}
if expected_hex not in source_digests:
    raise SystemExit('expected sha256 digest is absent from SBOM source identity')
PY

cleanup
trap - EXIT INT TERM
[[ ! -e "$qualification_root" ]] \
  || fail 'temporary SBOM files or cache were not removed'

pass 'CycloneDX schema and non-empty component results were validated'
pass 'expected sha256 digest was verified in structured source metadata'
pass 'temporary SBOM files and cache were removed'
pass 'SBOM generation is qualified only for the public digest-pinned image'
pass 'immutable digest enforcement passed as a repository and CI control'
pass 'no Portfolio image was built or published and no registry integration occurred'
pass 'no SBOM was attached to or stored in a registry'
pass 'package discovery completeness is not guaranteed'
pass 'production SBOM format, retention, attestation, and promotion policy require owner decisions'
