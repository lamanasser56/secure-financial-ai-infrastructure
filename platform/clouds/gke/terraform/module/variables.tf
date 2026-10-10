variable "project_id" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Use a valid GCP project ID."
  }
}

variable "project_number" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{6,20}$", var.project_number))
    error_message = "Use the numeric project number."
  }
}

variable "name" {
  type    = string
  default = "agent-platform"
}

variable "region" {
  type    = string
  default = "us-east1"
}

variable "zone" {
  type    = string
  default = "us-east1-b"
}

variable "gke_version" {
  description = "Exact reviewed REGULAR-channel version (no automatic choice)."
  type        = string
  validation {
    condition     = can(regex("^1\\.3[5-9]\\.[0-9]+-gke\\.[0-9]+$", var.gke_version))
    error_message = "Supply an exact reviewed GKE version."
  }
}

variable "machine_type" {
  type    = string
  default = "e2-standard-4"
}

variable "disk_size_gb" {
  type    = number
  default = 50
}

variable "initial_node_count" {
  description = "Creation size only; make up/down resizes 0<->1 afterwards."
  type        = number
  default     = 1
}

variable "deletion_protection" {
  description = "True while the platform lives; teardown sets false explicitly."
  type        = bool
  default     = true
}

variable "node_cidr" {
  type    = string
  default = "10.250.0.0/24"
}

variable "pod_cidr" {
  type    = string
  default = "10.251.0.0/20"
}

variable "service_cidr" {
  type    = string
  default = "10.252.0.0/24"
}

variable "control_plane_cidr" {
  type    = string
  default = "172.16.0.16/28"
}

variable "image_repository" {
  description = "Existing Artifact Registry repository that holds every platform image (no external registry at runtime)."
  type        = string
  default     = "sdp-evaluation-images"
}

variable "predict_role_id" {
  description = "New custom role ID (the C ID agentDemoPredict stays reserved)."
  type        = string
  default     = "agentPlatformPredict"
}

variable "redactor_service_account" {
  description = "Retained Sensitive Data Protection runtime account email."
  type        = string
}

variable "github_repository" {
  type    = string
  default = "lamanasser56/secure-financial-ai-infrastructure"
}

variable "github_repository_id" {
  type    = string
  default = "1401417840"
}

variable "ci_ref" {
  description = "The only Git ref whose workflow may obtain CI credentials."
  type        = string
  default     = "refs/heads/main"
}
