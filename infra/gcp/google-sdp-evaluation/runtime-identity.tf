resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = "google-sdp-runtime"
  display_name = "Synthetic SDP evaluation runtime"
  description  = "GKE Job identity for bounded synthetic text inspection only"
}

# Both regional content methods document only this project permission.
# No templates, storage, KMS, job creation or other DLP permissions are used.
resource "google_project_iam_custom_role" "sdp_content_use" {
  project     = var.project_id
  role_id     = "sdpContentUse"
  title       = "Synthetic SDP content use"
  description = "Billable inspect/deidentify content calls only"
  permissions = ["serviceusage.services.use"]
  stage       = "GA"
}

resource "google_project_iam_member" "runtime_content_use" {
  project = var.project_id
  role    = google_project_iam_custom_role.sdp_content_use.id
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_service_account_iam_member" "gke_runtime_impersonation" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.namespace}/${var.ksa_name}]"
}
