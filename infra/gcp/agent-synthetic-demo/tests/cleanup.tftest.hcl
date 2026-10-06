# Offline provider mocks only; this is not a cloud-backed plan or IAM proof.
mock_provider "google" {
  mock_resource "google_service_account" {
    defaults = {
      email = "google-agent-demo-model@synthetic-project.iam.gserviceaccount.com"
      name  = "projects/synthetic-project/serviceAccounts/google-agent-demo-model@synthetic-project.iam.gserviceaccount.com"
    }
  }
  mock_resource "google_project_iam_custom_role" {
    defaults = { name = "projects/synthetic-project/roles/agentDemoPredict" }
  }
}

variables {
  project_id = "synthetic-project"
}

run "create_fixture_state" {
  command = apply
  assert {
    condition     = length(google_service_account.model) == 1 && length(google_service_account_iam_member.gateway) == 1 && length(google_service_account_iam_member.redactor) == 1
    error_message = "Creation must contain only the declared temporary identities."
  }
}

run "complete_cleanup_retains_api" {
  command = apply
  variables {
    demo_identity_enabled = false
  }
  assert {
    condition     = length(google_service_account.model) == 0 && length(google_project_iam_custom_role.predict) == 0 && length(google_project_iam_member.predict) == 0 && length(google_service_account_iam_member.gateway) == 0 && length(google_service_account_iam_member.redactor) == 0
    error_message = "Complete cleanup must remove all five temporary resources."
  }
  assert {
    condition     = google_project_service.vertex.service == "aiplatform.googleapis.com" && google_project_service.vertex.disable_on_destroy == false
    error_message = "The shared Vertex API contract must remain in state."
  }
}
