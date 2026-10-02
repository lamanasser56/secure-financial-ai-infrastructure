terraform {
  backend "gcs" {
    prefix = "portfolio/google-sdp-evaluation-cluster"
  }
}
