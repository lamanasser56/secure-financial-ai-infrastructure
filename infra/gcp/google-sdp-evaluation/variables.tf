variable "project_id" {
  description = "Approved GCP project ID, supplied outside Git."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Use a valid GCP project ID."
  }
}

variable "project_number" {
  description = "Numeric project number for the GitHub WIF principal identifier."
  type        = string
  validation {
    condition     = can(regex("^[1-9][0-9]{5,19}$", var.project_number))
    error_message = "Use a numeric GCP project number."
  }
}

variable "region" {
  description = "Approved Artifact Registry and SDP region."
  type        = string
  default     = "us-east1"
  validation {
    condition     = var.region == "us-east1"
    error_message = "Only us-east1 is approved."
  }
}

variable "github_owner" {
  type    = string
  default = "lamanasser56"
  validation {
    condition     = var.github_owner == "lamanasser56"
    error_message = "The GitHub owner must match the reviewed repository."
  }
}

variable "github_repository" {
  type    = string
  default = "secure-financial-ai-infrastructure"
  validation {
    condition     = var.github_repository == "secure-financial-ai-infrastructure"
    error_message = "The GitHub repository must match the reviewed repository."
  }
}

variable "github_owner_id" {
  description = "Immutable numeric GitHub owner claim, verified out of band."
  type        = string
  validation {
    condition     = can(regex("^[1-9][0-9]{0,19}$", var.github_owner_id))
    error_message = "Provide the verified numeric GitHub owner ID."
  }
}

variable "github_repository_id" {
  description = "Immutable numeric GitHub repository claim, verified out of band."
  type        = string
  validation {
    condition     = can(regex("^[1-9][0-9]{0,19}$", var.github_repository_id))
    error_message = "Provide the verified numeric GitHub repository ID."
  }
}

variable "approved_source_commit" {
  description = "Exact source SHA from the explicitly approved execution bundle, supplied outside Git."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.approved_source_commit))
    error_message = "Supply the full lowercase reviewed source commit SHA."
  }
}

variable "github_branch" {
  type    = string
  default = "main"
  validation {
    condition     = var.github_branch == "main"
    error_message = "Only main is approved for the release workflow."
  }
}

variable "github_workflow" {
  type    = string
  default = "release-google-sdp-evaluation.yml"
  validation {
    condition     = var.github_workflow == "release-google-sdp-evaluation.yml"
    error_message = "Only the reviewed release workflow is approved."
  }
}

variable "artifact_repository_id" {
  description = "Dedicated immutable-tag Docker repository name."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,62}$", var.artifact_repository_id))
    error_message = "Use a valid Artifact Registry repository ID."
  }
}

variable "gke_cluster_name" {
  description = "Reviewed evaluation cluster name; informational, no cluster mutation."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,38}[a-z0-9]$", var.gke_cluster_name))
    error_message = "Use a valid GKE cluster name."
  }
}

variable "gke_cluster_location" {
  description = "Reviewed GKE zone or region; informational, no cluster mutation."
  type        = string
  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]+(-[a-z])?$", var.gke_cluster_location))
    error_message = "Use a valid GKE region or zone."
  }
}

variable "node_service_account_email" {
  description = "Reviewed GKE node image-pull identity; supplied outside Git, distinct from the evaluation runtime GSA."
  type        = string
  validation {
    condition = can(regex(
      "^([a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,28}[a-z0-9]\\.iam\\.gserviceaccount\\.com|[1-9][0-9]{5,19}-compute@developer\\.gserviceaccount\\.com)$",
      var.node_service_account_email
    )) && var.node_service_account_email != "google-sdp-runtime@${var.project_id}.iam.gserviceaccount.com" && var.node_service_account_email != "google-sdp-release@${var.project_id}.iam.gserviceaccount.com"
    error_message = "Use the reviewed GKE node GSA email, separate from the runtime and release identities."
  }
}

variable "namespace" {
  type    = string
  default = "google-sdp-evaluation"
  validation {
    condition     = var.namespace == "google-sdp-evaluation"
    error_message = "The evaluation namespace is fixed."
  }
}

# The KSA name is selected by the reviewed Job package contract.
variable "ksa_name" {
  type    = string
  default = "google-sdp-evaluation"
  validation {
    condition     = var.ksa_name == "google-sdp-evaluation"
    error_message = "The evaluation KSA name is fixed."
  }
}

variable "labels" {
  description = "Non-sensitive project labels for supported resources."
  type        = map(string)
  default = {
    purpose    = "synthetic-evaluation"
    managed_by = "terraform"
  }
  validation {
    condition = alltrue([
      for key, value in var.labels :
      can(regex("^[a-z][a-z0-9_-]{0,62}$", key)) && can(regex("^[a-z0-9_-]{0,63}$", value))
    ])
    error_message = "Labels must use lowercase GCP label syntax."
  }
}
