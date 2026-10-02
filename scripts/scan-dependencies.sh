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
    || fail "required dependency-scanning command is unavailable: $1"
}

readonly required_osv_scanner_version='2.4.0'
readonly dependency_manifest='requirements-dev.txt'

require_command git
require_command mktemp
require_command osv-scanner
require_command python3
require_command rm
require_command sed

repository_root="$(git rev-parse --show-toplevel 2>/dev/null)" \
  || fail 'run this script from a Git working tree'
cd "$repository_root"

[[ -f "$dependency_manifest" && -s "$dependency_manifest" ]] \
  || fail "required dependency manifest is unavailable or empty: $dependency_manifest"

actual_osv_scanner_version="$(
  osv-scanner --version 2>/dev/null \
    | sed -n 's/^osv-scanner version: //p' \
    | sed -n '1p'
)" || fail 'OSV-Scanner is present but its version cannot be determined'
[[ "$actual_osv_scanner_version" == "$required_osv_scanner_version" ]] \
  || fail "OSV-Scanner $required_osv_scanner_version is required; found $actual_osv_scanner_version"

printf 'Dependency scanner: OSV-Scanner %s\n' "$actual_osv_scanner_version"

temporary_base="${TMPDIR:-/tmp}"
[[ "$temporary_base" == /* && "$temporary_base" != '/' && -d "$temporary_base" ]] \
  || fail 'temporary base must be an existing absolute directory other than root'

scan_root="$(mktemp -d "$temporary_base/portfolio-dependency-scan.XXXXXXXX")"
[[ "$scan_root" == "$temporary_base"/portfolio-dependency-scan.* && -d "$scan_root" ]] \
  || fail 'mktemp returned an unexpected dependency-scan directory'

cleanup() {
  if [[ -n "${scan_root:-}" && -d "$scan_root" \
    && "$scan_root" == "$temporary_base"/portfolio-dependency-scan.* ]]; then
    rm -rf -- "$scan_root"
  fi
}
trap cleanup EXIT INT TERM

set +e
osv-scanner scan source \
  --lockfile="requirements.txt:$dependency_manifest" \
  --all-packages \
  --format=json \
  --verbosity=error \
  --output-file="$scan_root/report.json" \
  >"$scan_root/scanner-output.txt" 2>&1
scan_status=$?
set -e

if ((scan_status == 0)); then
  python3 - "$scan_root/report.json" <<'PY' \
    || fail 'dependency scanner returned an invalid or incomplete zero-finding report'
import json
from pathlib import Path
import sys

report_path = Path(sys.argv[1])
try:
    report = json.loads(report_path.read_text(encoding='utf-8'))
except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise SystemExit(f'invalid dependency scan report: {exc}') from exc

packages = [
    package
    for result in report.get('results', [])
    for package in result.get('packages', [])
]
if not packages:
    raise SystemExit('dependency scan report contains no parsed packages')
if any(package.get('vulnerabilities') for package in packages):
    raise SystemExit('zero-status dependency scan report unexpectedly contains findings')
PY
elif ((scan_status == 1)); then
  python3 - "$scan_root/report.json" <<'PY' \
    || fail 'dependency scanner reported findings but produced no valid sanitized metadata'
import json
from pathlib import Path
import sys

report_path = Path(sys.argv[1])
try:
    report = json.loads(report_path.read_text(encoding='utf-8'))
except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise SystemExit(f'invalid dependency scan report: {exc}') from exc

findings = set()
for result in report.get('results', []):
    for entry in result.get('packages', []):
        package = entry.get('package', {})
        for vulnerability in entry.get('vulnerabilities', []):
            findings.add((
                str(package.get('ecosystem', 'unknown')),
                str(package.get('name', 'unknown')),
                str(package.get('version', 'unknown')),
                str(vulnerability.get('id', 'unknown')),
            ))
if not findings:
    raise SystemExit('dependency scan report contains no structured findings')
for ecosystem, name, version, vulnerability_id in sorted(findings):
    print(
        f'VULNERABILITY: ecosystem={ecosystem} package={name} '
        f'version={version} id={vulnerability_id}',
        file=sys.stderr,
    )
PY
  fail 'dependency scan detected one or more known vulnerabilities'
else
  fail "dependency scanner execution or vulnerability-data retrieval failed with status $scan_status"
fi

cleanup
trap - EXIT INT TERM
[[ ! -e "$scan_root" ]] || fail 'temporary dependency-scan data was not removed'

pass 'declared CI dependencies passed known-vulnerability scanning'
