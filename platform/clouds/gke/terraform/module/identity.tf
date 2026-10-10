# Workload identities. Only the gateway reaches the model provider (Vertex); the redactor reuses the
# retained Sensitive Data Protection runtime account; apps and ops have no cloud identity at all.

resource "google_project_iam_custom_role" "predict" {
  project     = var.project_id
  role_id     = var.predict_role_id
  title       = "Agent platform model prediction"
  description = "Gateway only: call publisher models. Same permission set as the C agentDemoPredict role."
  permissions = ["aiplatform.endpoints.predict", "serviceusage.services.use"]
}

resource "google_service_account" "gateway" {
  project      = var.project_id
  account_id   = "${local.name}-gateway"
  display_name = "Agent platform gateway (Vertex via Workload Identity)"
}

resource "google_project_iam_member" "gateway_predict" {
  project = var.project_id
  role    = google_project_iam_custom_role.predict.id
  member  = "serviceAccount:${google_service_account.gateway.email}"
}

resource "google_service_account_iam_member" "gateway_wi" {
  service_account_id = google_service_account.gateway.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[platform/gateway]"
}

resource "google_service_account_iam_member" "redactor_wi" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${var.redactor_service_account}"
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[platform/redactor]"
}

# CI (GitHub Actions OIDC): a dedicated pool, provider and account. A separate pool means no other provider
# (including the retained C release provider) can ever map to this account. The account can only push to the
# image repository, sign with the attestor key and create attestations against the attestor note.
resource "google_iam_workload_identity_pool" "ci" {
  project                   = var.project_id
  workload_identity_pool_id = "${local.name}-ci"
  display_name              = "Agent platform CI"
}

resource "google_iam_workload_identity_pool_provider" "ci" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.ci.workload_identity_pool_id
  workload_identity_pool_provider_id = "${local.name}-ci"
  display_name                       = "Agent platform CI"
  attribute_mapping = {
    "google.subject"          = "assertion.sub"
    "attribute.repository_id" = "assertion.repository_id"
    "attribute.ref"           = "assertion.ref"
    "attribute.workflow_ref"  = "assertion.job_workflow_ref"
  }
  attribute_condition = "assertion.repository_id == '${var.github_repository_id}' && assertion.ref == '${var.ci_ref}' && assertion.job_workflow_ref.startsWith('${var.github_repository}/.github/workflows/agent-platform-images.yml@')"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "ci" {
  project      = var.project_id
  account_id   = "${local.name}-ci"
  display_name = "Agent platform CI (build, push, attest)"
}

resource "google_service_account_iam_member" "ci_wif" {
  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/${google_iam_workload_identity_pool.ci.workload_identity_pool_id}/attribute.repository_id/${var.github_repository_id}"
}

resource "google_artifact_registry_repository_iam_member" "ci_writer" {
  project    = var.project_id
  location   = local.region
  repository = var.image_repository
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.ci.email}"
}
