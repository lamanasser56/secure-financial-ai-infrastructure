terraform {
  backend "gcs" {
    prefix = "portfolio/agent-platform"
  }
}
