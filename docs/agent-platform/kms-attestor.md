# Binary Authorization attestor key (Cloud KMS): ownership and rotation

**Why KMS:**
- GKE admission cannot enforce keyless cosign signatures natively. The Sigstore check exists only in continuous
  validation, and it verifies with public keys.
- So CI keeps keyless cosign (identity = this repository's workflow on `main`, logged in Rekor) as the build
  signature, then creates a Binary Authorization attestation signed by a Cloud KMS key.
- Admission requires that attestation.

| Item | Value |
|---|---|
| Key ring / key | `agent-platform` / `binauthz-attestor` (us-east1), `EC_SIGN_P256_SHA256`, protection SOFTWARE |
| Owner | the project owner (sole administrator of the key ring); IAM changes go through Terraform only |
| CI rights | `roles/cloudkms.signerVerifier` on this key only (sign, never manage); `containeranalysis.notes.attacher` on the attestor note |
| Attestor / policy | `agent-platform-ci`; project singleton policy `REQUIRE_ATTESTATION`, `ENFORCED_BLOCK_AND_AUDIT_LOG`, Google system images exempt |
| Attested images | CI-built `agent-platform-app`, `agent-platform-ops`; the reused C-qualified gateway/database/redactor digests are attested once by the owner (`make attest`) after their existing signatures are verified |

## Rotation (manual: asymmetric keys do not auto-rotate)
1. Create key version N+1 (Terraform `google_kms_crypto_key_version` or the console). Version N stays enabled.
2. Add the N+1 public key to the attestor (Terraform `public_keys` block). Both versions are accepted.
3. Point CI and `make attest` at version N+1, then re-attest the running digests.
4. Confirm `make test` and a fresh `make up` pass admission. Disable version N, and destroy it after 24 h.

**Cadence:** on any suspected compromise, or before reuse beyond this portfolio. The platform's planned lifetime
ends 2026-11-08, which is shorter than any routine rotation period.

## Teardown
- Key versions are scheduled for destruction (24 h).
- The key ring itself cannot be deleted in GCP. It costs nothing once no enabled versions remain, and the final
  inventory records it as such.
