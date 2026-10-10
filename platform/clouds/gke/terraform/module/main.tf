# Phase E (ADR-008): persistent private GKE agent platform. Reusable module; the root in
# infra/gcp/agent-platform supplies the project, names and exact versions.
# Derived from the C-proven infra/gcp/google-sdp-evaluation-cluster root (private nodes, private
# endpoint + IAM-only DNS endpoint, Dataplane V2 + FQDN policy, Workload Identity, Shielded nodes).
# Differences: no Cloud NAT (Google APIs through Private Google Access only), persistent-disk CSI on
# for Postgres, Managed Prometheus on, Binary Authorization enforced, one pool scaled 0<->1 outside
# Terraform, deletion protection on by default.

locals {
  name   = var.name
  region = var.region
  zone   = var.zone
}

resource "google_project_service" "required" {
  for_each           = toset(["binaryauthorization.googleapis.com", "cloudkms.googleapis.com", "containeranalysis.googleapis.com"])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_compute_network" "platform" {
  project                 = var.project_id
  name                    = local.name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "platform" {
  project                  = var.project_id
  name                     = local.name
  region                   = local.region
  network                  = google_compute_network.platform.id
  ip_cidr_range            = var.node_cidr
  private_ip_google_access = true # the only egress path: Google APIs (Artifact Registry, Vertex, DLP, Logging)
  secondary_ip_range {
    range_name    = "${local.name}-pods"
    ip_cidr_range = var.pod_cidr
  }
  secondary_ip_range {
    range_name    = "${local.name}-services"
    ip_cidr_range = var.service_cidr
  }
  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.1
    metadata             = "EXCLUDE_ALL_METADATA"
  }
}

resource "google_service_account" "node" {
  project      = var.project_id
  account_id   = "${local.name}-node"
  display_name = "Agent platform GKE node"
}

resource "google_project_iam_member" "node" {
  project = var.project_id
  role    = "roles/container.defaultNodeServiceAccount"
  member  = "serviceAccount:${google_service_account.node.email}"
}

resource "google_artifact_registry_repository_iam_member" "node_reader" {
  project    = var.project_id
  location   = local.region
  repository = var.image_repository
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.node.email}"
}

resource "google_container_cluster" "platform" {
  project                    = var.project_id
  name                       = local.name
  location                   = local.zone
  network                    = google_compute_network.platform.id
  subnetwork                 = google_compute_subnetwork.platform.id
  networking_mode            = "VPC_NATIVE"
  datapath_provider          = "ADVANCED_DATAPATH"
  enable_fqdn_network_policy = true
  min_master_version         = var.gke_version
  deletion_protection        = var.deletion_protection
  enable_shielded_nodes      = true
  enable_legacy_abac         = false
  resource_labels = {
    purpose    = "agent-platform"
    managed_by = "terraform"
    lifecycle  = "portfolio-until-2026-11-08"
  }
  release_channel {
    channel = "REGULAR"
  }
  ip_allocation_policy {
    cluster_secondary_range_name  = "${local.name}-pods"
    services_secondary_range_name = "${local.name}-services"
    stack_type                    = "IPV4"
  }
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = true
    master_ipv4_cidr_block  = var.control_plane_cidr
  }
  control_plane_endpoints_config {
    dns_endpoint_config {
      allow_external_traffic    = true # IAM-authenticated operator (port-forward), never anonymous
      enable_k8s_tokens_via_dns = false
      enable_k8s_certs_via_dns  = false
    }
    ip_endpoints_config {
      enabled = false
    }
  }
  # No master_authorized_networks_config: IP endpoints are disabled entirely (DNS endpoint with IAM only), so the
  # API keeps no authorized-networks state and declaring it only produced a perpetual diff.
  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }
  dns_config {
    cluster_dns = "KUBE_DNS"
  }
  addons_config {
    http_load_balancing {
      disabled = true # no Ingress / load balancer path exists
    }
    horizontal_pod_autoscaling {
      disabled = true
    }
    dns_cache_config {
      enabled = false
    }
    gce_persistent_disk_csi_driver_config {
      enabled = true # Postgres PersistentVolume (Retain)
    }
  }
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }
  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = true
    }
  }
  remove_default_node_pool = true
  initial_node_count       = 1
  node_config {
    machine_type    = var.machine_type
    disk_size_gb    = var.disk_size_gb
    disk_type       = "pd-balanced"
    image_type      = "COS_CONTAINERD"
    service_account = google_service_account.node.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    metadata = {
      disable-legacy-endpoints = "true"
    }
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
  timeouts {
    create = "45m"
    delete = "45m"
  }
  depends_on = [google_project_iam_member.node, google_binary_authorization_policy.platform]
}

resource "google_container_node_pool" "platform" {
  project            = var.project_id
  name               = "work"
  location           = local.zone
  cluster            = google_container_cluster.platform.name
  initial_node_count = var.initial_node_count
  version            = var.gke_version
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  upgrade_settings {
    max_surge       = 0
    max_unavailable = 1
  }
  node_config {
    machine_type    = var.machine_type
    disk_size_gb    = var.disk_size_gb
    disk_type       = "pd-balanced"
    image_type      = "COS_CONTAINERD"
    service_account = google_service_account.node.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels = {
      workload = "agent-platform"
    }
    metadata = {
      disable-legacy-endpoints = "true"
    }
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
  lifecycle {
    # make up / make down resize 0<->1 outside Terraform; Terraform never fights the on-demand size.
    ignore_changes = [node_count, initial_node_count]
  }
  timeouts {
    create = "30m"
    delete = "30m"
  }
}
