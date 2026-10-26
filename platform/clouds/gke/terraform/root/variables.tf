variable "project_id" {
  type = string
}

variable "project_number" {
  type = string
}

variable "gke_version" {
  type = string
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "assessment_mode" {
  description = "Create only the disposable project's empty local image repository and redactor identity; release images remain in the reviewed source registry."
  type        = bool
  default     = false
}

variable "ci_ref" {
  type    = string
  default = "refs/heads/main"
}
