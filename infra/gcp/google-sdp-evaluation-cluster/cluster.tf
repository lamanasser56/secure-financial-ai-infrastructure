# Proposed evaluation resources only. No existing VPC or cluster is imported.
provider "google" {
  project = var.project_id
  region  = "us-east1"
}

resource "google_compute_network" "evaluation" {
  count                   = var.evaluation_cluster_enabled ? 1 : 0
  name                    = "google-sdp-evaluation"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "evaluation" {
  count                    = var.evaluation_cluster_enabled ? 1 : 0
  name                     = "google-sdp-evaluation"
  region                   = "us-east1"
  network                  = google_compute_network.evaluation[0].id
  ip_cidr_range            = "10.240.0.0/24"
  private_ip_google_access = true
  secondary_ip_range {
    range_name    = "evaluation-pods"
    ip_cidr_range = "10.241.0.0/20"
  }
  secondary_ip_range {
    range_name    = "evaluation-services"
    ip_cidr_range = "10.242.0.0/24"
  }
  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.1
    metadata             = "EXCLUDE_ALL_METADATA"
  }
}

# A working route for negative probes, not an egress authorization control.
resource "google_compute_address" "nat" {
  count        = var.evaluation_cluster_enabled ? 1 : 0
  name         = "google-sdp-evaluation-nat"
  region       = "us-east1"
  address_type = "EXTERNAL"
}

resource "google_compute_router" "evaluation" {
  count   = var.evaluation_cluster_enabled ? 1 : 0
  name    = "google-sdp-evaluation"
  region  = "us-east1"
  network = google_compute_network.evaluation[0].id
}

resource "google_compute_router_nat" "evaluation" {
  count                              = var.evaluation_cluster_enabled ? 1 : 0
  name                               = "google-sdp-evaluation"
  region                             = "us-east1"
  router                             = google_compute_router.evaluation[0].name
  nat_ip_allocate_option             = "MANUAL_ONLY"
  nat_ips                            = [google_compute_address.nat[0].self_link]
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"
  subnetwork {
    name                    = google_compute_subnetwork.evaluation[0].id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

resource "google_service_account" "node" {
  disabled     = !var.evaluation_cluster_enabled
  account_id   = "google-sdp-evaluation-node"
  display_name = "Synthetic evaluation GKE node"
}

# Official minimum node role. The identity root grants repository reader only.
resource "google_project_iam_member" "node" {
  count   = var.evaluation_cluster_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/container.defaultNodeServiceAccount"
  member  = "serviceAccount:${google_service_account.node.email}"
}

resource "google_container_cluster" "evaluation" {
  count                      = var.evaluation_cluster_enabled ? 1 : 0
  name                       = "google-sdp-evaluation"
  location                   = "us-east1-b"
  network                    = google_compute_network.evaluation[0].id
  subnetwork                 = google_compute_subnetwork.evaluation[0].id
  networking_mode            = "VPC_NATIVE"
  datapath_provider          = "ADVANCED_DATAPATH"
  enable_fqdn_network_policy = true
  min_master_version         = var.gke_version
  deletion_protection        = false # Explicit bounded cleanup, this root only.
  enable_shielded_nodes      = true
  enable_legacy_abac         = false
  resource_labels = {
    purpose    = "synthetic-evaluation"
    managed_by = "terraform"
  }
  release_channel {
    channel = "REGULAR"
  }
  ip_allocation_policy {
    cluster_secondary_range_name  = "evaluation-pods"
    services_secondary_range_name = "evaluation-services"
    stack_type                    = "IPV4"
  }
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = true
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }
  control_plane_endpoints_config {
    dns_endpoint_config {
      allow_external_traffic    = true # IAM-authenticated operator, not anonymous.
      enable_k8s_tokens_via_dns = false
      enable_k8s_certs_via_dns  = false
    }
    ip_endpoints_config {
      enabled = false
    }
  }
  master_authorized_networks_config {
    gcp_public_cidrs_access_enabled      = false
    private_endpoint_enforcement_enabled = true
  }
  dns_config {
    cluster_dns = "KUBE_DNS"
  }
  addons_config {
    http_load_balancing {
      disabled = true
    }
    horizontal_pod_autoscaling {
      disabled = true
    }
    dns_cache_config {
      enabled = false
    }
    gce_persistent_disk_csi_driver_config {
      enabled = false
    }
  }
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }
  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = false
    }
  }
  remove_default_node_pool = true
  initial_node_count       = 1
  node_version             = var.gke_version
  node_config {
    machine_type    = "e2-standard-2"
    disk_size_gb    = 20
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
  depends_on = [google_project_iam_member.node, google_compute_router_nat.evaluation]
}

resource "google_container_node_pool" "evaluation" {
  count      = var.evaluation_cluster_enabled ? 1 : 0
  name       = "evaluation"
  location   = "us-east1-b"
  cluster    = google_container_cluster.evaluation[0].name
  node_count = 1
  version    = var.gke_version
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  upgrade_settings {
    max_surge       = 0
    max_unavailable = 1
  }
  node_config {
    machine_type    = "e2-standard-2"
    disk_size_gb    = 20
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
    create = "30m"
    delete = "30m"
  }
}
