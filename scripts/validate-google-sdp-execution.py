"""Offline contracts for the proposed owner profile and dedicated GKE root."""

import json
from pathlib import Path
import re
import sys

import yaml
from jsonschema import validate as validate_schema


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(root=ROOT):
    profile = json.loads((root / "evaluation/google-sdp/execution-profile.json").read_text())
    require(set(profile) == {"profile", "status", "owner", "repository", "requires_explicit_complete_bundle_approval", "independent_review", "separation_of_duties_proven", "manual_release_only", "exact_reviewed_commit_required", "committed_corpus_only", "maximum_sdk_operations", "maximum_live_jobs", "application_retries", "job_retries", "real_data_authorized", "production_authorized", "presidio_authoritative", "egress", "maximum_cluster_hours", "incremental_operator_stop_limit_usd", "retain_evaluation_cluster"}, "closed owner profile")
    require(profile["profile"] == "synthetic-owner-approval-v1" and profile["status"] == "proposed", "proposal is not approval")
    require(profile["owner"] == "lamanasser56" and profile["repository"] == "lamanasser56/secure-financial-ai-infrastructure", "exact repository owner")
    for key in ("requires_explicit_complete_bundle_approval", "manual_release_only", "exact_reviewed_commit_required", "committed_corpus_only", "presidio_authoritative"):
        require(profile[key] is True, f"required control: {key}")
    for key in ("independent_review", "separation_of_duties_proven", "real_data_authorized", "production_authorized", "retain_evaluation_cluster"):
        require(profile[key] is False, f"unproven/prohibited claim: {key}")
    for key, value in (("maximum_sdk_operations", 18), ("maximum_live_jobs", 1), ("application_retries", 0), ("job_retries", 0), ("maximum_cluster_hours", 6), ("incremental_operator_stop_limit_usd", 5)):
        require(type(profile[key]) is int and profile[key] == value, f"bounded control: {key}")
    require(profile["egress"] == "gke-native-dns-derived-ip-port", "native IP/port boundary")
    module = root / "infra/gcp/google-sdp-evaluation-cluster"
    tf = {path.name: path.read_text() for path in module.glob("*.tf")}
    require(set(tf) == {"backend.tf", "versions.tf", "variables.tf", "cluster.tf", "outputs.tf"}, "reviewed root files")
    source = "\n".join(tf.values())
    require(set(re.findall(r'resource "([^"]+)" "([^"]+)"', source)) == {
        ("google_compute_network", "evaluation"), ("google_compute_subnetwork", "evaluation"),
        ("google_compute_address", "nat"), ("google_compute_router", "evaluation"),
        ("google_compute_router_nat", "evaluation"), ("google_service_account", "node"),
        ("google_project_iam_member", "node"), ("google_container_cluster", "evaluation"),
        ("google_container_node_pool", "evaluation"),
    }, "nine dedicated resources only")
    require('backend "gcs"' in tf["backend.tf"] and 'prefix = "portfolio/google-sdp-evaluation-cluster"' in tf["backend.tf"], "separate remote-state prefix")
    require(not re.search(r'(?m)^\s*bucket\s*=', tf["backend.tf"]), "no committed backend bucket")
    require('version = "= 8.5.0"' in tf["versions.tf"] and 'version     = "8.5.0"' in (module / ".terraform.lock.hcl").read_text(), "existing provider lock")
    require((module / ".terraform.lock.hcl").read_bytes() == (root / "infra/gcp/google-sdp-evaluation/.terraform.lock.hcl").read_bytes(), "same qualified Google provider")
    for field, value in (
        ("datapath_provider", '"ADVANCED_DATAPATH"'), ("enable_fqdn_network_policy", "true"),
        ("networking_mode", '"VPC_NATIVE"'), ("cluster_dns", '"KUBE_DNS"'),
        ("enable_private_nodes", "true"), ("enable_private_endpoint", "true"),
        ("enable_shielded_nodes", "true"), ("enable_legacy_abac", "false"),
        ("enable_k8s_tokens_via_dns", "false"), ("enable_k8s_certs_via_dns", "false"),
        ("gcp_public_cidrs_access_enabled", "false"), ("node_count", "1"),
        ("machine_type", '"e2-standard-2"'), ("disk_size_gb", "20"),
        ("max_surge", "0"), ("max_unavailable", "1"),
        ("enable_secure_boot", "true"), ("enable_integrity_monitoring", "true"),
        ("service_account", "google_service_account.node.email"),
        ("mode", '"GKE_METADATA"'), ("min_master_version", "var.gke_version"),
        ("remove_default_node_pool", "true"), ("initial_node_count", "1"),
        ("auto_create_subnetworks", "false"), ("private_ip_google_access", "true"),
        ("source_subnetwork_ip_ranges_to_nat", '"LIST_OF_SUBNETWORKS"'),
    ):
        require(re.search(rf'(?m)^\s*{field}\s*=\s*{re.escape(value)}\s*(?:#.*)?$', tf["cluster.tf"]), f"missing dedicated cluster control: {field}")
    require(re.search(r'ip_endpoints_config\s*\{\s*enabled\s*=\s*false\s*\}', source), "DNS-only IAM endpoint")
    require(re.search(r'dns_cache_config\s*\{\s*enabled\s*=\s*false\s*\}', source), "cluster kube-dns path only")
    require('location' in source and re.search(r'location\s*=\s*"us-east1-b"', source), "bounded cluster location")
    require(set(re.findall(r'roles/[a-zA-Z0-9_.]+', source)) == {"roles/container.defaultNodeServiceAccount"}, "minimum dedicated node role")
    require('member  = "serviceAccount:${google_service_account.node.email}"' in source, "node role scope")
    require('account_id   = "google-sdp-evaluation-node"' in source, "separate node identity")
    require(len(re.findall(r'(?m)^\s*count\s*=\s*var.evaluation_cluster_enabled \? 1 : 0$', source)) == 8, "eight bounded cleanup resources")
    require(re.search(r'disabled\s*=\s*!var.evaluation_cluster_enabled', source), "retained node identity disabled on cleanup")
    require(len(re.findall(r'(?m)^\s*service_account\s*=\s*google_service_account.node.email$', source)) == 2, "bootstrap and final pool use the dedicated node identity")
    require(len(re.findall(r'disable-legacy-endpoints\s*=\s*"true"', source)) == 2, "both pools disable legacy metadata")
    require(not re.search(r'(?i)google_service_account_key|private_key|credentials\s*=|provisioner|local-exec|remote-exec|terraform_remote_state|data "|import\s*\{|\bautoscaling\s*\{', source), "no credential, import, implicit execution or expansion")
    require(not re.search(r'project-[0-9a-f]{8}-|[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com', source), "no environment values")
    require(re.search(r'(?m)^project_id\s*=\s*"REPLACE_WITH_APPROVED_PROJECT_ID"$', (module / "example.tfvars").read_text()), "placeholder inputs only")


def validate_region(root=ROOT):
    """One committed deployment selection; an old approval cannot select it at runtime."""
    contract = json.loads((root / "evaluation/google-sdp/deployment.json").read_text())
    validate_schema(contract, json.loads((root / "evaluation/google-sdp/deployment.schema.json").read_text()))
    require(contract == {"schema_version": 1, "region": "us-east1", "endpoint": "dlp.us-east1.rep.googleapis.com"}, "exact amended deployment")
    directory = root / "kubernetes/apps/google-sdp-evaluation"
    config = yaml.safe_load((directory / "configmap.yaml").read_text())["data"]
    require(config == {"region": contract["region"], "endpoint": contract["endpoint"], "synthetic_corpus_path": "/app/evaluation/google-sdp/corpus.json"}, "matching regional ConfigMap")
    policy = yaml.safe_load((directory / "fqdnnetworkpolicy.yaml").read_text())
    require(policy["spec"]["egress"] == [{"matches": [{"name": contract["endpoint"]}], "ports": [{"protocol": "TCP", "port": 443}]}], "matching native FQDN boundary")
    probe = (root / "scripts/probe-google-sdp-egress.py").read_text()
    require(f'ENDPOINT = "{contract["endpoint"]}"' in probe, "matching zero-call probe")
    workflow = (root / ".github/workflows/release-google-sdp-evaluation.yml").read_text()
    require(workflow.count('"$RELEASE_REGION" == us-east1') == 2, "both release jobs restrict deployment region")
    require('us-east1-docker.pkg.dev' in workflow and 'locations/us-east1/repositories/' in workflow, "matching registry host and API path")
    variables = (root / "infra/gcp/google-sdp-evaluation/variables.tf").read_text()
    require('var.region == "us-east1"' in variables, "matching registry Terraform validation")
    renderer = (root / "scripts/render-google-sdp-evaluation-job.sh").read_text()
    require('^us-east1-docker' in renderer and '"us-east1-docker.pkg.dev/$project/"' in renderer, "matching digest renderer")
    dockerfile = (root / "docker/google-sdp-evaluation/Dockerfile").read_text()
    build = (root / "scripts/build-google-sdp-evaluation-image.sh").read_text()
    for name in ("deployment.json", "deployment.schema.json"):
        require(f"evaluation/google-sdp/{name}" in dockerfile and f"evaluation/google-sdp/{name}" in build, "deployment selection is part of the image and content key")


def main():
    try:
        validate()
        validate_region()
    except Exception:
        print("FAIL: proposed synthetic execution contract", file=sys.stderr)
        return 1
    print("PASS: proposed owner profile and dedicated native GKE contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
