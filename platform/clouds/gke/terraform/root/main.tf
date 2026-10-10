# Phase E root (ADR-008). New names and state prefix: independent of the W18 leftovers and the locked
# google-sdp-evaluation-cluster state. Bucket is supplied at init (-backend-config=bucket=...).
provider "google" {
  project = var.project_id
  region  = "us-east1"
}

module "platform" {
  source                   = "../module"
  project_id               = var.project_id
  project_number           = var.project_number
  gke_version              = var.gke_version
  redactor_service_account = "google-sdp-runtime@${var.project_id}.iam.gserviceaccount.com"
  deletion_protection      = var.deletion_protection
  ci_ref                   = var.ci_ref
}
