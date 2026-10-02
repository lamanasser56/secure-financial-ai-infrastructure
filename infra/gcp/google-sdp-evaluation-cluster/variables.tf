variable "project_id" {
  description = "Approved project ID, supplied outside Git."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Use a valid GCP project ID."
  }
}

variable "gke_version" {
  description = "Exact reviewed REGULAR-channel version from read-only serverConfig inventory."
  type        = string
  validation {
    condition     = can(regex("^1\\.35\\.[0-9]+-gke\\.[0-9]+$", var.gke_version))
    error_message = "Supply an exact reviewed GKE 1.35 version; do not choose a version automatically."
  }
}

variable "evaluation_cluster_enabled" {
  description = "False for approved cleanup: remove compute/network/node role and disable the retained node GSA."
  type        = bool
  default     = true
}
