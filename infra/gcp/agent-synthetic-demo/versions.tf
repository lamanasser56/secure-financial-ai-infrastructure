terraform {
  required_version = "= 1.16.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 8.5.0"
    }
  }
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = "us-east1"
}
