# Private paths to the two regional API endpoints the workloads use. Private Google Access does not serve
# endpoints ending in rep.googleapis.com, and the platform has no Cloud NAT, so each one gets a Private
# Service Connect regional endpoint (an internal address in the node subnet) and a private Cloud DNS zone
# whose apex resolves the public hostname to that address inside this VPC only. The clients keep their
# fixed hostnames (TLS and the FQDN egress policies are unchanged); only resolution and routing change.
# https://cloud.google.com/vpc/docs/access-regional-google-apis-endpoints
locals {
  regional_apis = {
    dlp    = "dlp.${local.region}.rep.googleapis.com" # redactor (Sensitive Data Protection adapter)
    vertex = "aiplatform.us.rep.googleapis.com"       # gateway (LiteLLM vertex_location: us)
  }
}

resource "google_project_service" "private_endpoints" {
  for_each           = toset(["networkconnectivity.googleapis.com", "dns.googleapis.com"])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_network_connectivity_regional_endpoint" "api" {
  for_each          = local.regional_apis
  project           = var.project_id
  name              = "${local.name}-${each.key}"
  location          = local.region
  target_google_api = each.value
  access_type       = "REGIONAL"
  network           = google_compute_network.platform.id
  subnetwork        = google_compute_subnetwork.platform.id
  depends_on        = [google_project_service.private_endpoints]
}

resource "google_dns_managed_zone" "api" {
  for_each   = local.regional_apis
  project    = var.project_id
  name       = "${local.name}-${each.key}"
  dns_name   = "${each.value}."
  visibility = "private"
  private_visibility_config {
    networks {
      network_url = google_compute_network.platform.id
    }
  }
  depends_on = [google_project_service.private_endpoints]
}

resource "google_dns_record_set" "api" {
  for_each     = local.regional_apis
  project      = var.project_id
  managed_zone = google_dns_managed_zone.api[each.key].name
  name         = "${each.value}."
  type         = "A"
  ttl          = 300
  rrdatas      = [google_network_connectivity_regional_endpoint.api[each.key].address]
}
