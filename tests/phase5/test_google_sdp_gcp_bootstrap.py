"""Offline fail-closed contracts for the synthetic Google SDP GCP root module."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "infra/gcp/google-sdp-evaluation"
VALIDATOR = ROOT / "scripts/validate-google-sdp-gcp-bootstrap.sh"
K8S = ROOT / "kubernetes/apps/google-sdp-evaluation"


def fixture():
    temporary = tempfile.TemporaryDirectory(prefix="portfolio-sdp-gcp-test-")
    root = Path(temporary.name)
    target = root / "infra/gcp/google-sdp-evaluation"
    shutil.copytree(MODULE, target, ignore=shutil.ignore_patterns(".terraform"))
    (root / "scripts").mkdir()
    shutil.copy2(VALIDATOR, root / "scripts/validate-google-sdp-gcp-bootstrap.sh")
    (root / "tests/phase5").mkdir(parents=True)
    (root / "kubernetes/apps/google-sdp-evaluation").mkdir(parents=True)
    service_account = yaml.safe_load((K8S / "serviceaccount.yaml").read_text())
    job = yaml.safe_load((K8S / "job.yaml").read_text())
    # Keep the committed Kubernetes identity unchanged in the offline fixture.
    (root / "kubernetes/apps/google-sdp-evaluation/serviceaccount.yaml").write_text(yaml.safe_dump(service_account))
    (root / "kubernetes/apps/google-sdp-evaluation/job.yaml").write_text(yaml.safe_dump(job))
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    return temporary, root, target


def validate(root):
    return subprocess.run(
        ["bash", str(root / "scripts/validate-google-sdp-gcp-bootstrap.sh")],
        cwd=root, capture_output=True, text=True, check=False,
    )


class GCPBootstrapContractTests(unittest.TestCase):
    def test_existing_job_and_terraform_identity_are_consistent(self):
        result = subprocess.run(["bash", str(VALIDATOR)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_reviewed_fixture_passes_without_cloud_access(self):
        temporary, root, _ = fixture()
        try:
            result = validate(root)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        finally:
            temporary.cleanup()

    def test_unsafe_module_mutations_are_rejected(self):
        def mutate(target, case):
            if case == "real_project":
                value = "project-" + "12345678-1234-1234-1234-123456789abc"
                (target / "example.tfvars").write_text(f'project_id = "{value}"\n')
            elif case == "state":
                (target / "terraform.tfstate").write_text("{}")
            elif case == "plan":
                (target / "release.tfplan").write_text("plan")
            elif case == "real_tfvars":
                (target / "actual.tfvars").write_text('project_id = "real-project-name"\n')
            else:
                filename, before, after = {
                    "unapproved_region": ("variables.tf", 'var.region == "us-east1"', 'var.region == "me-central2"'),
                    "service_key": ("github-wif.tf", 'resource "google_service_account" "release"', 'resource "google_service_account_key" "bad" {}\nresource "google_service_account" "release"'),
                    "owner_role": ("artifact-registry.tf", 'roles/artifactregistry.writer', 'roles/owner'),
                    "public_member": ("artifact-registry.tf", 'member     = "serviceAccount:${google_service_account.release.email}"', 'member     = "allUsers"'),
                    "mutable_registry": ("artifact-registry.tf", 'immutable_tags = true', 'immutable_tags = false'),
                    "weak_workflow_trust": ("github-wif.tf", '"assertion.workflow_ref ==', '"assertion.missing_workflow_ref =='),
                    "weak_event_trust": ("github-wif.tf", "assertion.event_name == 'workflow_dispatch'", "assertion.event_name == 'push'"),
                    "weak_source_trust": ("github-wif.tf", "assertion.sha == '${var.approved_source_commit}'", "assertion.sha != '${var.approved_source_commit}'"),
                    "weak_environment_trust": ("github-wif.tf", "assertion.sub == 'repo:", "assertion.sub == 'unapproved:"),
                    "legacy_subject": ("github-wif.tf", "repo:${var.github_owner}@${var.github_owner_id}/${var.github_repository}@${var.github_repository_id}:environment:", "repo:${var.github_owner}/${var.github_repository}:environment:"),
                    "mixed_identities": ("artifact-registry.tf", 'member     = "serviceAccount:${google_service_account.release.email}"', 'member     = "serviceAccount:${google_service_account.runtime.email}"'),
                    "runtime_registry": ("runtime-identity.tf", 'permissions = ["serviceusage.services.use"]', 'permissions = ["serviceusage.services.use", "artifactregistry.repositories.uploadArtifacts"]'),
                    "node_writer": ("artifact-registry.tf", 'role       = "roles/artifactregistry.reader"', 'role       = "roles/artifactregistry.writer"'),
                    "runtime_pull_identity": ("artifact-registry.tf", 'member     = "serviceAccount:${var.node_service_account_email}"', 'member     = "serviceAccount:${google_service_account.runtime.email}"'),
                    "alternate_namespace": ("variables.tf", 'variable "namespace" {\n  type    = string\n  default = "google-sdp-evaluation"', 'variable "namespace" {\n  type    = string\n  default = "production"'),
                    "alternate_ksa": ("variables.tf", 'variable "ksa_name" {\n  type    = string\n  default = "google-sdp-evaluation"', 'variable "ksa_name" {\n  type    = string\n  default = "default"'),
                    "unrelated_api": ("services.tf", 'service            = "dlp.googleapis.com"', 'service            = "aiplatform.googleapis.com"'),
                    "backend_bucket": ("backend.tf", 'prefix = "portfolio/google-sdp-evaluation"', 'bucket = "real-backend-bucket"\n    prefix = "portfolio/google-sdp-evaluation"'),
                }[case]
                path = target / filename
                original = path.read_text()
                if before not in original:
                    raise AssertionError(f"missing mutation anchor for {case}")
                path.write_text(original.replace(before, after, 1))

        cases = (
            "real_project", "state", "plan", "real_tfvars", "service_key",
            "owner_role", "public_member", "mutable_registry", "weak_workflow_trust",
            "weak_event_trust", "mixed_identities", "runtime_registry",
            "alternate_namespace", "alternate_ksa", "unrelated_api", "backend_bucket",
            "node_writer", "runtime_pull_identity", "weak_environment_trust",
            "weak_source_trust",
            "legacy_subject", "unapproved_region",
        )
        for case in cases:
            with self.subTest(case=case):
                temporary, root, target = fixture()
                try:
                    mutate(target, case)
                    result = validate(root)
                    self.assertNotEqual(result.returncode, 0, case)
                finally:
                    temporary.cleanup()

    def test_validation_paths_contain_no_cloud_mutation(self):
        for path in (VALIDATOR, Path(__file__)):
            content = path.read_text(encoding="utf-8")
            self.assertNotRegex(content, r"(?m)^\s*(?:terraform\s+apply|gcloud\s+(?:services|iam|artifacts|container)|gh\s+(?:variable|workflow)|docker\s+push|kubectl\s+apply)\b")


if __name__ == "__main__":
    unittest.main()
