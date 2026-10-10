# Binary Authorization: only attested image digests run. GKE admission cannot enforce keyless cosign
# signatures natively (the Sigstore check exists only in continuous validation, with public keys), so
# CI verifies the keyless cosign signature, then attests the digest with a Cloud KMS key (PKIX attestor).
# Key ownership: the project owner; CI may only sign. Rotation: asymmetric keys do not auto-rotate; see
# docs/agent-platform/kms-attestor.md (add a version, add its public key to the attestor, re-attest, disable the old one).

resource "google_kms_key_ring" "platform" {
  project    = var.project_id
  name       = local.name
  location   = local.region
  depends_on = [google_project_service.required]
}

resource "google_kms_crypto_key" "attestor" {
  name                       = "binauthz-attestor"
  key_ring                   = google_kms_key_ring.platform.id
  purpose                    = "ASYMMETRIC_SIGN"
  destroy_scheduled_duration = "86400s" # teardown: versions destroyed 24 h after scheduling
  version_template {
    algorithm        = "EC_SIGN_P256_SHA256"
    protection_level = "SOFTWARE"
  }
}

data "google_kms_crypto_key_version" "attestor" {
  crypto_key = google_kms_crypto_key.attestor.id
}

resource "google_kms_crypto_key_iam_member" "ci_signer" {
  crypto_key_id = google_kms_crypto_key.attestor.id
  role          = "roles/cloudkms.signerVerifier"
  member        = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_container_analysis_note" "attestor" {
  project = var.project_id
  name    = "${local.name}-attestor"
  attestation_authority {
    hint {
      human_readable_name = "Agent platform CI (Trivy + SBOM + keyless cosign verified)"
    }
  }
  depends_on = [google_project_service.required]
}

resource "google_container_analysis_note_iam_member" "ci_attacher" {
  project = var.project_id
  note    = google_container_analysis_note.attestor.name
  role    = "roles/containeranalysis.notes.attacher"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_project_iam_member" "ci_occurrences" {
  project = var.project_id
  role    = "roles/containeranalysis.occurrences.editor"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_binary_authorization_attestor" "platform" {
  project = var.project_id
  name    = "${local.name}-ci"
  attestation_authority_note {
    note_reference = google_container_analysis_note.attestor.name
    public_keys {
      id = data.google_kms_crypto_key_version.attestor.id
      pkix_public_key {
        public_key_pem      = data.google_kms_crypto_key_version.attestor.public_key[0].pem
        signature_algorithm = data.google_kms_crypto_key_version.attestor.public_key[0].algorithm
      }
    }
  }
}

resource "google_binary_authorization_attestor_iam_member" "ci_viewer" {
  project  = var.project_id
  attestor = google_binary_authorization_attestor.platform.name
  role     = "roles/binaryauthorization.attestorsViewer"
  member   = "serviceAccount:${google_service_account.ci.email}"
}

# Project singleton policy. Only clusters created with PROJECT_SINGLETON_POLICY_ENFORCE evaluate it.
# Google-maintained system images are exempt through the global policy.
resource "google_binary_authorization_policy" "platform" {
  project                       = var.project_id
  global_policy_evaluation_mode = "ENABLE"
  default_admission_rule {
    evaluation_mode         = "REQUIRE_ATTESTATION"
    enforcement_mode        = "ENFORCED_BLOCK_AND_AUDIT_LOG"
    require_attestations_by = [google_binary_authorization_attestor.platform.name]
  }
}
