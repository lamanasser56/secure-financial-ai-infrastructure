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

variable "ci_ref" {
  type    = string
  default = "refs/heads/main"
}
