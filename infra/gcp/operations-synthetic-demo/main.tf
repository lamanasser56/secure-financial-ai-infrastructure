# Proposed additional identity contract only; no apply authority is embedded.
variable "project_id" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,61}[a-z0-9]$", var.project_id))
    error_message = "An exact reviewed project is required."
  }
}

resource "google_project_service" "vertex" {
  project            = var.project_id
  service            = "aiplatform.googleapis.com"
  disable_on_destroy = false
}

resource "google_service_account" "model" {
  project      = var.project_id
  account_id   = "google-agent-demo-model"
  display_name = "Temporary fixed synthetic gateway model identity"
}

resource "google_project_iam_custom_role" "predict" {
  project     = var.project_id
  role_id     = "agentDemoPredict"
  title       = "Temporary synthetic demo prediction"
  permissions = ["aiplatform.endpoints.predict", "serviceusage.services.use"]
}

resource "google_project_iam_member" "predict" {
  project = var.project_id
  role    = google_project_iam_custom_role.predict.name
  member  = "serviceAccount:${google_service_account.model.email}"
}

resource "google_service_account_iam_member" "gateway" {
  service_account_id = google_service_account.model.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[google-agent-demo/google-agent-demo-gateway]"
}
