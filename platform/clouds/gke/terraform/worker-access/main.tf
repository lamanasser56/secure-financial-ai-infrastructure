# Independent IAM stack: no VM, disk, cluster or teardown resource is owned here.
# Apply only in the original private project; the persistent worker is never destroyed by this stack.
terraform {
  required_version = ">= 1.16.5, < 1.17.0"
  required_providers {
    google = { source = "hashicorp/google", version = "= 8.5.0" }
  }
}

variable "project_id" {
  type = string
}
variable "worker_name" {
  type    = string
  default = "secure-infra-worker"
}
variable "worker_zone" {
  type    = string
  default = "us-east1-b"
}
variable "ci_service_account" {
  type    = string
  default = "agent-platform-ci"
}

provider "google" {
  project               = var.project_id
  region                = "us-east1"
  user_project_override = true
  billing_project       = var.project_id
}

locals { member = "serviceAccount:${var.ci_service_account}@${var.project_id}.iam.gserviceaccount.com" }

resource "google_project_service" "iap" {
  project            = var.project_id
  service            = "iap.googleapis.com"
  disable_on_destroy = false
}

# gcloud SSH needs project metadata read even when login is bound only to an instance.
resource "google_project_iam_custom_role" "worker_project_read" {
  project     = var.project_id
  role_id     = "sfaiWorkerCIProjectRead"
  title       = "Secure infrastructure worker project metadata read"
  permissions = ["compute.projects.get", "resourcemanager.projects.get"]
}

resource "google_project_iam_member" "worker_project_read" {
  project = var.project_id
  role    = google_project_iam_custom_role.worker_project_read.id
  member  = local.member
}

resource "google_compute_instance_iam_member" "worker_os_admin" {
  project       = var.project_id
  zone          = var.worker_zone
  instance_name = var.worker_name
  role          = "roles/compute.osAdminLogin"
  member        = local.member
}

resource "google_iap_tunnel_instance_iam_member" "worker_iap" {
  project    = var.project_id
  zone       = var.worker_zone
  instance   = var.worker_name
  role       = "roles/iap.tunnelResourceAccessor"
  member     = local.member
  depends_on = [google_project_service.iap]
}
