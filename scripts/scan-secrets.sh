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
    || fail "required secret-scanning command is unavailable: $1"
}

readonly required_gitleaks_version='8.30.1'

require_command git
require_command gitleaks

repository_root="$(git rev-parse --show-toplevel 2>/dev/null)" \
  || fail 'run this script from a Git working tree'
cd "$repository_root"

actual_gitleaks_version="$(gitleaks version 2>/dev/null)" \
  || fail 'Gitleaks is present but its version cannot be determined'
[[ "$actual_gitleaks_version" == "$required_gitleaks_version" ]] \
  || fail "Gitleaks $required_gitleaks_version is required; found $actual_gitleaks_version"

printf 'Secret scanner: Gitleaks %s\n' "$actual_gitleaks_version"

gitleaks dir \
  --no-banner \
  --no-color \
  --redact=100 \
  --verbose \
  --exit-code=1 \
  . \
  || fail 'dedicated current-repository secret scan detected a finding'
pass 'current repository content passed dedicated secret scanning'

gitleaks git \
  --no-banner \
  --no-color \
  --redact=100 \
  --verbose \
  --exit-code=1 \
  --log-opts='--all' \
  . \
  || fail 'dedicated Git-history secret scan detected a finding'
pass 'relevant committed Git history passed dedicated secret scanning'

pass 'dedicated secret scanning completed with redacted output'
