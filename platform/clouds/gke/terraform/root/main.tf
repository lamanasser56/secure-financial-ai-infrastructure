# Phase E root (ADR-008). New names and state prefix: independent of the W18 leftovers and the locked
# google-sdp-evaluation-cluster state. Bucket is supplied at init (-backend-config=bucket=...).
provider "google" {
  project = var.project_id
  region  = "us-east1"
  # User ADC needs an explicit quota project for some APIs (Binary Authorization); bill the platform project.
  user_project_override = true
  billing_project       = var.project_id
}

resource "google_artifact_registry_repository" "assessment" {
  count         = var.assessment_mode ? 1 : 0
  project       = var.project_id
  location      = "us-east1"
  repository_id = "sdp-evaluation-images"
  format        = "DOCKER"
  description   = "Empty disposable repository for the assessment platform module's node-reader binding"
}

resource "google_service_account" "assessment_redactor" {
  count        = var.assessment_mode ? 1 : 0
  project      = var.project_id
  account_id   = "google-sdp-runtime"
  display_name = "Disposable assessment redactor"
}

resource "google_project_iam_member" "assessment_redactor_dlp" {
  count   = var.assessment_mode ? 1 : 0
  project = var.project_id
  role    = "roles/dlp.user"
  member  = "serviceAccount:${google_service_account.assessment_redactor[0].email}"
}

module "platform" {
  source                   = "../module"
  project_id               = var.project_id
  project_number           = var.project_number
  gke_version              = var.gke_version
  redactor_service_account = var.assessment_mode ? google_service_account.assessment_redactor[0].email : "google-sdp-runtime@${var.project_id}.iam.gserviceaccount.com"
  deletion_protection      = var.deletion_protection
  ci_ref                   = var.ci_ref
  depends_on               = [google_artifact_registry_repository.assessment]
}
