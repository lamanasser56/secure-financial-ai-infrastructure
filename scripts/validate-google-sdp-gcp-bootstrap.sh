#!/usr/bin/env bash
set -Eeuo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
if (($# > 1)); then
  printf 'usage: validate-google-sdp-gcp-bootstrap.sh [MODULE_DIRECTORY]\n' >&2
  exit 2
fi
module=${1:-$root/infra/gcp/google-sdp-evaluation}
python3 - "$root" "$module" <<'PY'
from pathlib import Path
import re
import subprocess
import sys
import yaml

root = Path(sys.argv[1])
module = Path(sys.argv[2])


def require(condition, message):
    if not condition:
        raise SystemExit(f"GCP bootstrap contract: {message}")


required = {
    "backend.tf", "versions.tf", "providers.tf", "variables.tf", "services.tf",
    "artifact-registry.tf", "github-wif.tf", "runtime-identity.tf", "outputs.tf",
    "README.md", "example.tfvars", ".terraform.lock.hcl",
}
require(module.is_dir(), "missing root module")
require(required.issubset({p.name for p in module.iterdir()}), "missing required module file")
tf = {name: (module / name).read_text(encoding="utf-8") for name in required if name.endswith(".tf")}
source = "\n".join(tf.values())
example = (module / "example.tfvars").read_text(encoding="utf-8")
lock = (module / ".terraform.lock.hcl").read_text(encoding="utf-8")

require('backend "gcs"' in tf["backend.tf"], "GCS backend is required")
require(not re.search(r"(?m)^\s*bucket\s*=", tf["backend.tf"]), "backend bucket must not be committed")
require('version = "= 8.5.0"' in tf["versions.tf"] and 'version     = "8.5.0"' in lock, "provider pin and lock must match")
require('required_version = ">= 1.16.5, < 1.17.0"' in tf["versions.tf"], "Terraform compatibility must be pinned")
require(not re.search(r'(?m)^\s*project\s*=\s*"', source), "project ID must come from the validated input")
require(not re.search(r"project-[0-9a-f]{8}-[0-9a-f-]{10,}|[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com", source + example), "real project or GSA identity found")
require(not re.search(r"(?i)(private_key|credentials_json|google_service_account_key|BEGIN PRIVATE KEY|\.json\s*credentials)", source + example), "credential or service-account key found")
require(not re.search(r"(?m)^\s*(?:project_id|project_number|github_owner_id|github_repository_id|gke_cluster_name|node_service_account_email)\s*=\s*\"(?!REPLACE_WITH_)", example), "example tfvars contains an environment identifier")
require(not re.search(r"roles/(?:owner|editor|viewer)\b|allUsers|allAuthenticatedUsers|/\*\"", source, re.IGNORECASE), "broad IAM member or role found")
require(set(re.findall(r"roles/[A-Za-z0-9_.]+", source)) == {"roles/artifactregistry.writer", "roles/artifactregistry.reader", "roles/iam.workloadIdentityUser"}, "unapproved predefined IAM role")

visible = subprocess.check_output(
    ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
).decode("utf-8").split("\0")
for relative in filter(None, visible):
    path = Path(relative)
    require(".terraform" not in path.parts and not re.search(r"\.(?:tfstate|tfplan)(?:\.|$)|\.tfvars\.json$", path.name), "state, plan or provider cache is Git-visible")
    require(not (path.suffix == ".tfvars" and path.name != "example.tfvars"), "real tfvars is Git-visible")

services = set(re.findall(r'(?m)^\s*service\s*=\s*"([a-z.]+googleapis.com)"', tf["services.tf"]))
require(services == {"artifactregistry.googleapis.com", "dlp.googleapis.com", "iamcredentials.googleapis.com", "sts.googleapis.com"}, "unexpected or missing enabled API")
require(tf["services.tf"].count("disable_on_destroy = false") == 4, "shared APIs must remain enabled on destroy")
registry = tf["artifact-registry.tf"]
require('location      = var.region' in registry and 'format        = "DOCKER"' in registry and 'mode          = "STANDARD_REPOSITORY"' in registry, "wrong registry location or format")
require(re.search(r"docker_config\s*\{\s*immutable_tags\s*=\s*true", registry), "registry tags must be immutable")
require('role       = "roles/artifactregistry.writer"' in registry and 'member     = "serviceAccount:${google_service_account.release.email}"' in registry, "release writer must be repository-scoped")
require("google_artifact_registry_repository_iam_member" in registry and "google_project_iam_member" not in registry, "writer binding must use repository IAM")
require('resource "google_artifact_registry_repository_iam_member" "node_reader"' in registry and 'role       = "roles/artifactregistry.reader"' in registry and 'member     = "serviceAccount:${var.node_service_account_email}"' in registry, "node image-pull identity must have repository-scoped read access")
require('var.node_service_account_email != "google-sdp-runtime@${var.project_id}.iam.gserviceaccount.com"' in tf["variables.tf"] and 'var.node_service_account_email != "google-sdp-release@${var.project_id}.iam.gserviceaccount.com"' in tf["variables.tf"], "node identity must remain separate from evaluation identities")
require("older_than = \"30d\"" in registry and 'tag_state  = "UNTAGGED"' in registry and 'tag_prefixes = ["sha-"]' in registry, "cleanup policy must protect releases and bound abandoned digests")

wif = tf["github-wif.tf"]
for required_claim in (
    "assertion.repository_owner ==", "assertion.repository_owner_id ==",
    "assertion.repository ==", "assertion.repository_id ==",
    "assertion.ref == 'refs/heads/", "assertion.ref_type == 'branch'",
    "assertion.event_name == 'workflow_dispatch'", "assertion.workflow_ref ==",
    "assertion.sha == '${var.approved_source_commit}'",
    "assertion.sub == 'repo:${var.github_owner}@${var.github_owner_id}/${var.github_repository}@${var.github_repository_id}:environment:google-sdp-evaluation-release'",
):
    require(required_claim in wif, f"missing WIF trust claim: {required_claim}")
require('"attribute.repository_id"    = "assertion.repository_id"' in wif, "numeric repository claim must be mapped")
require('issuer_uri = "https://token.actions.githubusercontent.com"' in wif, "wrong GitHub issuer")
require('role               = "roles/iam.workloadIdentityUser"' in wif and "/attribute.repository_id/${var.github_repository_id}" in wif, "release impersonation must use exact repository ID")
require("principalSet://iam.googleapis.com/projects/${var.project_number}" in wif, "WIF principal requires numeric project number")
require("google_service_account_key" not in wif and "google_service_account.runtime" not in wif, "GitHub trust must not reach runtime identity")

runtime = tf["runtime-identity.tf"]
require('account_id   = "google-sdp-runtime"' in runtime and 'account_id   = "google-sdp-release"' in wif, "release and runtime GSAs must be distinct")
require(re.search(r'permissions\s*=\s*\["serviceusage.services.use"\]', runtime), "runtime custom role must have only the documented content-call permission")
require('member  = "serviceAccount:${google_service_account.runtime.email}"' in runtime, "runtime role must bind only the runtime GSA")
require('member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.namespace}/${var.ksa_name}]"' in runtime, "GKE binding must use the exact namespace and KSA")
require("artifactregistry" not in runtime.lower() and "roles/dlp.user" not in runtime, "runtime may not have registry or broad DLP access")

variables = tf["variables.tf"]
for name, expected in (
    ("region", "us-east1"), ("github_owner", "lamanasser56"),
    ("github_repository", "secure-financial-ai-infrastructure"),
    ("github_branch", "main"), ("github_workflow", "release-google-sdp-evaluation.yml"),
    ("namespace", "google-sdp-evaluation"), ("ksa_name", "google-sdp-evaluation"),
):
    block = re.search(rf'variable "{name}"\s*\{{(.*?)\n\}}', variables, re.S)
    require(block is not None, f"missing {name} variable")
    require(re.search(rf'default\s*=\s*"{re.escape(expected)}"', block.group(1)), f"{name} is not fixed to the reviewed value")
    require(f'var.{name} == "{expected}"' in block.group(1), f"{name} override validation is missing")

service_account = yaml.safe_load((root / "kubernetes/apps/google-sdp-evaluation/serviceaccount.yaml").read_text())
job = yaml.safe_load((root / "kubernetes/apps/google-sdp-evaluation/job.yaml").read_text())
ksa = service_account["metadata"]["name"]
job_ksa = job["spec"]["template"]["spec"]["serviceAccountName"]
require(ksa == job_ksa == "google-sdp-evaluation", "Terraform KSA does not match the existing ServiceAccount and Job")
require(service_account["metadata"]["namespace"] == job["metadata"]["namespace"] == "google-sdp-evaluation", "Terraform namespace does not match the existing ServiceAccount and Job")
require('value       = "serviceAccount:${var.project_id}.svc.id.goog[${var.namespace}/${var.ksa_name}]"' in tf["outputs.tf"], "KSA identity output must match the IAM member")
require(re.search(r'namespace\s*=\s*"google-sdp-evaluation"', example) and re.search(r'ksa_name\s*=\s*"google-sdp-evaluation"', example), "example identity must match the existing KSA")

outputs = tf["outputs.tf"]
for name in ("github_wif_provider_resource_name", "release_gsa_email", "runtime_gsa_email", "artifact_registry_repository_url", "ksa_annotation_value", "github_environment_variable_names", "gke_ksa_binding_identity"):
    require(f'output "{name}"' in outputs, f"missing contract output {name}")
for name in ("GOOGLE_SDP_RELEASE_WIF_PROVIDER", "GOOGLE_SDP_RELEASE_SERVICE_ACCOUNT", "GOOGLE_SDP_RELEASE_PROJECT_ID"):
    require(name in outputs, f"missing workflow environment variable {name}")

for path in (root / "scripts/validate-google-sdp-gcp-bootstrap.sh", root / "tests/phase5/test_google_sdp_gcp_bootstrap.py"):
    if path.exists():
        require(not re.search(r"(?m)^\s*(?:terraform\s+apply|gcloud\s+(?:services|iam|artifacts|container)|gh\s+(?:variable|workflow)|docker\s+push|kubectl\s+apply)\b", path.read_text()), "validator or tests contain a mutating command")

print("PASS: synthetic Google SDP GCP bootstrap contract")
PY
