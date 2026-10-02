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
    || fail "required image-scanning command is unavailable: $1"
}

readonly required_trivy_version='0.72.0'
# This threshold is used only to qualify the Trivy integration against a public
# third-party image. It is not the approved production promotion threshold for
# future Portfolio images; that threshold requires a separate owner-approved
# decision. LOW and MEDIUM findings may exist outside this qualification
# threshold. A status 0 means no findings at the configured qualification
# threshold, not that the image is vulnerability-free.
readonly qualification_severity_policy='HIGH,CRITICAL'

(($# == 1)) || fail 'provide exactly one immutable image reference'
readonly image_reference="$1"

[[ "$image_reference" =~ ^[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$ ]] \
  || fail 'image reference must use an immutable sha256 digest'

require_command mktemp
require_command python3
require_command rm
require_command sed
require_command trivy

actual_trivy_version="$(
  trivy --version 2>/dev/null \
    | sed -n 's/^Version: //p' \
    | sed -n '1p'
)" || fail 'Trivy is present but its version cannot be determined'
[[ "$actual_trivy_version" == "$required_trivy_version" ]] \
  || fail "Trivy $required_trivy_version is required; found $actual_trivy_version"

printf 'Image scanner: Trivy %s\n' "$actual_trivy_version"
printf 'Image target: %s\n' "$image_reference"

temporary_base="${TMPDIR:-/tmp}"
[[ "$temporary_base" == /* && "$temporary_base" != '/' && -d "$temporary_base" ]] \
  || fail 'temporary base must be an existing absolute directory other than root'

scan_root="$(mktemp -d "$temporary_base/portfolio-image-scan.XXXXXXXX")"
[[ "$scan_root" == "$temporary_base"/portfolio-image-scan.* && -d "$scan_root" ]] \
  || fail 'mktemp returned an unexpected image-scan directory'

cleanup() {
  if [[ -n "${scan_root:-}" && -d "$scan_root" \
    && "$scan_root" == "$temporary_base"/portfolio-image-scan.* ]]; then
    rm -rf -- "$scan_root"
  fi
}
trap cleanup EXIT INT TERM

set +e
trivy image \
  --image-src remote \
  --scanners vuln \
  --severity "$qualification_severity_policy" \
  --exit-code 1 \
  --format json \
  --output "$scan_root/report.json" \
  --cache-dir "$scan_root/cache" \
  --no-progress \
  --skip-version-check \
  "$image_reference" \
  >"$scan_root/scanner-output.txt" 2>&1
scan_status=$?
set -e

if ((scan_status == 0)); then
  python3 - "$scan_root/report.json" "$image_reference" <<'PY' \
    || fail 'Trivy returned an invalid or incomplete qualification report'
import json
from pathlib import Path
import sys

report_path = Path(sys.argv[1])
expected_image = sys.argv[2]
try:
    report = json.loads(report_path.read_text(encoding='utf-8'))
except (OSError, UnicodeError, json.JSONDecodeError):
    raise SystemExit('invalid structured image scan report')

if report.get('SchemaVersion') != 2:
    raise SystemExit('unexpected Trivy report schema')
if report.get('ArtifactType') != 'container_image':
    raise SystemExit('Trivy report does not describe a container image')
if report.get('ArtifactName') != expected_image:
    raise SystemExit('Trivy report target does not match the requested immutable image')
results = report.get('Results')
if not isinstance(results, list) or not results:
    raise SystemExit('Trivy report contains no parsed image results')
if any(result.get('Vulnerabilities') for result in results):
    raise SystemExit('successful Trivy report unexpectedly contains qualification findings')
PY
elif ((scan_status == 1)); then
  python3 - "$scan_root/report.json" <<'PY' \
    || fail 'Trivy reported findings but produced no valid sanitized metadata'
import json
from pathlib import Path
import sys

report_path = Path(sys.argv[1])
try:
    report = json.loads(report_path.read_text(encoding='utf-8'))
except (OSError, UnicodeError, json.JSONDecodeError):
    raise SystemExit('invalid structured image scan report')

findings = set()
for result in report.get('Results') or []:
    ecosystem = str(result.get('Type', 'unknown'))
    for vulnerability in result.get('Vulnerabilities') or []:
        findings.add((
            ecosystem,
            str(vulnerability.get('PkgName', 'unknown')),
            str(vulnerability.get('InstalledVersion', 'unknown')),
            str(vulnerability.get('VulnerabilityID', 'unknown')),
            str(vulnerability.get('Severity', 'unknown')),
        ))
if not findings:
    raise SystemExit('Trivy report contains no structured policy findings')
for ecosystem, package, version, vulnerability_id, severity in sorted(findings):
    print(
        f'VULNERABILITY: ecosystem={ecosystem} package={package} '
        f'version={version} id={vulnerability_id} severity={severity}',
        file=sys.stderr,
    )
PY
  fail 'image scan detected HIGH or CRITICAL findings; qualification-image results may reflect vulnerability-database drift, and policy must not be weakened'
else
  fail "Trivy database retrieval, image retrieval, parsing, or scanner execution failed with status $scan_status"
fi

cleanup
trap - EXIT INT TERM
[[ ! -e "$scan_root" ]] || fail 'temporary Trivy report or cache data was not removed'

pass 'no HIGH or CRITICAL findings were reported at the provisional qualification threshold'
pass 'immutable image retrieval and structured Trivy qualification passed'
