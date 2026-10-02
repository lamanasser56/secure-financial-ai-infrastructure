output "github_wif_provider_resource_name" {
  description = "Set GOOGLE_SDP_RELEASE_WIF_PROVIDER to this value."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "release_gsa_email" {
  description = "Set GOOGLE_SDP_RELEASE_SERVICE_ACCOUNT to this value."
  value       = google_service_account.release.email
}

output "runtime_gsa_email" {
  description = "Use only as the trusted KSA annotation value at render time."
  value       = google_service_account.runtime.email
}

output "artifact_registry_repository_url" {
  description = "Region, project and repository path for the release workflow."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.evaluation.repository_id}"
}

output "ksa_annotation_value" {
  description = "Value for iam.gke.io/gcp-service-account on the dedicated KSA."
  value       = google_service_account.runtime.email
}

output "github_environment_variable_names" {
  description = "Names only; Terraform does not change GitHub variables."
  value = {
    provider        = "GOOGLE_SDP_RELEASE_WIF_PROVIDER"
    service_account = "GOOGLE_SDP_RELEASE_SERVICE_ACCOUNT"
    project_id      = "GOOGLE_SDP_RELEASE_PROJECT_ID"
  }
}

output "gke_ksa_binding_identity" {
  description = "Exact KSA identity allowed to impersonate the runtime GSA."
  value       = "serviceAccount:${var.project_id}.svc.id.goog[${var.namespace}/${var.ksa_name}]"
}
