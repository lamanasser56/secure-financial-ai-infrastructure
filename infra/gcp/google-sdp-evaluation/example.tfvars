# Copy outside Git and replace every REPLACE_WITH value. Never commit real tfvars.
project_id             = "REPLACE_WITH_PROJECT_ID"
project_number         = "REPLACE_WITH_PROJECT_NUMBER"
github_owner_id        = "REPLACE_WITH_VERIFIED_GITHUB_OWNER_ID"
github_repository_id   = "REPLACE_WITH_VERIFIED_GITHUB_REPOSITORY_ID"
approved_source_commit = "REPLACE_WITH_APPROVED_SOURCE_COMMIT"

region                     = "me-central2"
artifact_repository_id     = "sdp-evaluation-images"
gke_cluster_name           = "REPLACE_WITH_GKE_CLUSTER_NAME"
gke_cluster_location       = "us-east1-b"
node_service_account_email = "REPLACE_WITH_GKE_NODE_SERVICE_ACCOUNT_EMAIL"
namespace                  = "google-sdp-evaluation"
ksa_name                   = "google-sdp-evaluation"

labels = {
  purpose    = "synthetic-evaluation"
  managed_by = "terraform"
}
