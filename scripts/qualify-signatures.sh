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
    || fail "required signature-qualification command is unavailable: $1"
}

readonly required_cosign_version='v2.6.2'

require_command cosign
require_command chmod
require_command grep
require_command mktemp
require_command python3
require_command rm
require_command sed
require_command tr

actual_cosign_version="$(
  cosign version 2>/dev/null \
    | sed -n 's/^GitVersion:[[:space:]]*//p' \
    | sed -n '1p'
)" || fail 'Cosign is present but its version cannot be determined'
[[ "$actual_cosign_version" == "$required_cosign_version" ]] \
  || fail "Cosign $required_cosign_version is required; found $actual_cosign_version"

printf 'Signature tool: Cosign %s\n' "$actual_cosign_version"

temporary_base="${TMPDIR:-/tmp}"
[[ "$temporary_base" == /* && "$temporary_base" != '/' \
  && -d "$temporary_base" ]] \
  || fail 'temporary base must be an existing absolute directory other than root'

qualification_root="$(mktemp -d "$temporary_base/portfolio-signature.XXXXXXXX")"
[[ "$qualification_root" == "$temporary_base"/portfolio-signature.* \
  && -d "$qualification_root" ]] \
  || fail 'mktemp returned an unexpected signature qualification directory'

cleanup() {
  unset COSIGN_PASSWORD
  if [[ -n "${qualification_root:-}" && -d "$qualification_root" \
    && "$qualification_root" == "$temporary_base"/portfolio-signature.* ]]; then
    rm -rf -- "$qualification_root"
  fi
}
trap cleanup EXIT INT TERM

readonly key_prefix="$qualification_root/qualification"
readonly private_key="$key_prefix.key"
readonly public_key="$key_prefix.pub"
readonly payload="$qualification_root/payload.txt"
readonly signature="$qualification_root/payload.sig"
readonly keygen_log="$qualification_root/keygen.log"
readonly signing_log="$qualification_root/signing.log"
readonly positive_log="$qualification_root/positive-verification.log"
readonly negative_log="$qualification_root/negative-verification.log"
readonly final_log="$qualification_root/final-verification.log"

COSIGN_PASSWORD="$(python3 - <<'PY'
import secrets

print(secrets.token_urlsafe(48))
PY
)" || fail 'temporary key password generation failed'
export COSIGN_PASSWORD

cosign generate-key-pair \
  --output-key-prefix "$key_prefix" \
  >"$keygen_log" 2>&1 \
  || fail 'temporary Cosign key generation failed'

[[ -s "$private_key" && -s "$public_key" ]] \
  || fail 'Cosign did not create the expected temporary key pair'
chmod 0600 "$private_key"
chmod 0644 "$public_key"

printf 'Portfolio synthetic signature qualification payload: original\n' >"$payload"

cosign sign-blob \
  --key "$private_key" \
  --output-signature "$signature" \
  --tlog-upload=false \
  --yes \
  "$payload" \
  >"$signing_log" 2>&1 \
  || fail 'Cosign failed to sign the temporary qualification payload'
[[ -s "$signature" ]] || fail 'Cosign produced no temporary signature'

cosign verify-blob \
  --key "$public_key" \
  --signature "$signature" \
  --insecure-ignore-tlog \
  "$payload" \
  >"$positive_log" 2>&1 \
  || fail 'Cosign failed to verify the valid temporary signature'

printf 'Portfolio synthetic signature qualification payload: tampered\n' >"$payload"
set +e
cosign verify-blob \
  --key "$public_key" \
  --signature "$signature" \
  --insecure-ignore-tlog \
  "$payload" \
  >"$negative_log" 2>&1
negative_status=$?
set -e

((negative_status != 0)) \
  || fail 'Cosign accepted a signature after only the payload content changed'
grep -Fq 'invalid signature when validating ASN.1 encoded signature' \
  "$negative_log" \
  || fail 'Cosign negative verification did not report the expected signature-mismatch category'

printf 'Portfolio synthetic signature qualification payload: original\n' >"$payload"
cosign verify-blob \
  --key "$public_key" \
  --signature "$signature" \
  --insecure-ignore-tlog \
  "$payload" \
  >"$final_log" 2>&1 \
  || fail 'Cosign failed final verification after restoring the original payload'

signature_value="$(tr -d '\r\n' <"$signature")"
[[ -n "$signature_value" ]] || fail 'temporary signature content is empty'
for log_file in \
  "$keygen_log" \
  "$signing_log" \
  "$positive_log" \
  "$negative_log" \
  "$final_log"; do
  ! grep -Fq -- "$COSIGN_PASSWORD" "$log_file" \
    || fail 'temporary key password appeared in captured output'
  ! grep -Fq -- "$signature_value" "$log_file" \
    || fail 'raw signature appeared in captured output'
  ! grep -Fq -- 'BEGIN ENCRYPTED COSIGN PRIVATE KEY' "$log_file" \
    || fail 'private key material appeared in captured output'
  ! grep -Fq -- 'Portfolio synthetic signature qualification payload' "$log_file" \
    || fail 'synthetic payload content appeared in captured output'
done
unset signature_value

cleanup
trap - EXIT INT TERM
[[ -z "${COSIGN_PASSWORD+x}" ]] \
  || fail 'temporary key password remained in the execution environment'
[[ ! -e "$qualification_root" ]] \
  || fail 'temporary cryptographic material or qualification directory was not removed'

pass 'temporary synthetic payload was signed and verified successfully'
pass 'tampered payload was rejected for the expected signature-mismatch category'
pass 'valid signature verification passed again after restoring the original payload'
pass 'captured output contained no password, private key, payload, or raw signature material'
pass 'all temporary cryptographic material and qualification files were removed'
pass 'no transparency-log upload, registry access, or Portfolio image signing occurred'
pass 'production trust-root and key-lifecycle decisions remain unimplemented'
