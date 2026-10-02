resource "google_service_account" "release" {
  project      = var.project_id
  account_id   = "google-sdp-release"
  display_name = "Synthetic SDP image release"
  description  = "GitHub OIDC release identity; no runtime access or keys"
}

resource "google_iam_workload_identity_pool" "release" {
  project                   = var.project_id
  workload_identity_pool_id = "google-sdp-release"
  display_name              = "Synthetic SDP release"
  description               = "Only the reviewed GitHub release workflow"
  disabled                  = false
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.release.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-release"
  display_name                       = "GitHub manual SDP release"
  disabled                           = false

  # Check the protected environment subject as well as independent branch,
  # numeric identity and workflow claims. Numeric IDs resist name reuse.
  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.repository_id"    = "assertion.repository_id"
    "attribute.repository_owner" = "assertion.repository_owner_id"
  }
  attribute_condition = join(" && ", [
    "assertion.repository_owner == '${var.github_owner}'",
    "assertion.repository_owner_id == '${var.github_owner_id}'",
    "assertion.repository == '${var.github_owner}/${var.github_repository}'",
    "assertion.repository_id == '${var.github_repository_id}'",
    "assertion.ref == 'refs/heads/${var.github_branch}'",
    "assertion.ref_type == 'branch'",
    "assertion.event_name == 'workflow_dispatch'",
    "assertion.workflow_ref == '${var.github_owner}/${var.github_repository}/.github/workflows/${var.github_workflow}@refs/heads/${var.github_branch}'",
    "assertion.sub == 'repo:${var.github_owner}/${var.github_repository}:environment:google-sdp-evaluation-release'",
  ])

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_release_impersonation" {
  service_account_id = google_service_account.release.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/${google_iam_workload_identity_pool.release.workload_identity_pool_id}/attribute.repository_id/${var.github_repository_id}"

  depends_on = [google_iam_workload_identity_pool_provider.github]
}
