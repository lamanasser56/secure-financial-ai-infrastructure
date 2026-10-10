output "cluster_name" {
  value = google_container_cluster.platform.name
}

output "cluster_location" {
  value = google_container_cluster.platform.location
}

output "node_pool" {
  value = google_container_node_pool.platform.name
}

output "control_plane_cidr" {
  description = "ops-agent egress to the API server (overlay NetworkPolicy ipBlock)."
  value       = var.control_plane_cidr
}

output "gateway_service_account" {
  value = google_service_account.gateway.email
}

output "ci_service_account" {
  value = google_service_account.ci.email
}

output "ci_workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.ci.name
}

output "attestor" {
  value = google_binary_authorization_attestor.platform.name
}

output "attestor_key_version" {
  value = data.google_kms_crypto_key_version.attestor.name
}
