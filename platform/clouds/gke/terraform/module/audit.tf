# Audit events (one JSON line per event with "audit_event") from the platform workloads go to a dedicated,
# 30-day log bucket. Nothing is written to local files or SQLite.

resource "google_logging_project_bucket_config" "audit" {
  project        = var.project_id
  location       = local.region
  bucket_id      = "${local.name}-audit"
  retention_days = 30
}

resource "google_logging_project_sink" "audit" {
  project                = var.project_id
  name                   = "${local.name}-audit"
  destination            = "logging.googleapis.com/${google_logging_project_bucket_config.audit.id}"
  filter                 = "resource.type=\"k8s_container\" AND resource.labels.cluster_name=\"${local.name}\" AND jsonPayload.audit_event:*"
  unique_writer_identity = true
}
