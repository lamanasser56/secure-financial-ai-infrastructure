terraform {
  required_version = ">= 1.16.5, < 1.17.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 8.5.0"
    }
  }
}
