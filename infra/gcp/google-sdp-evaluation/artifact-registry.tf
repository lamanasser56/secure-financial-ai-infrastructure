resource "google_artifact_registry_repository" "evaluation" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repository_id
  description   = "Synthetic Google SDP evaluation image only"
  format        = "DOCKER"
  mode          = "STANDARD_REPOSITORY"
  labels        = var.labels

  docker_config {
    immutable_tags = true
  }

  # Remove abandoned, untagged digests after the review window. Immutable
  # commit-tagged releases are retained until separately approved cleanup.
  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "delete-untagged-after-30-days"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "30d"
    }
  }
  cleanup_policies {
    id     = "keep-commit-releases"
    action = "KEEP"
    condition {
      tag_state    = "TAGGED"
      tag_prefixes = ["sha-"]
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.artifact_registry]
}

resource "google_artifact_registry_repository_iam_member" "release_writer" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.evaluation.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.release.email}"
}

# Kubelet image pulls use the node identity, independently of Pod Workload Identity.
resource "google_artifact_registry_repository_iam_member" "node_reader" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.evaluation.repository_id
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${var.node_service_account_email}"
}
