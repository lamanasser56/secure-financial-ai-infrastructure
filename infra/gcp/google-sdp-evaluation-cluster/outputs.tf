output "cluster_name" {
  value = var.evaluation_cluster_enabled ? google_container_cluster.evaluation[0].name : null
}

output "cluster_location" {
  value = var.evaluation_cluster_enabled ? google_container_cluster.evaluation[0].location : null
}

output "node_service_account_email" {
  description = "Input to the identity root's repository-scoped node reader binding."
  value       = google_service_account.node.email
}
