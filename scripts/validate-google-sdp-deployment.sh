#!/usr/bin/env bash
set -Eeuo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
if (($# > 1)); then
  echo 'usage: validate-google-sdp-deployment.sh [RENDERED_MANIFEST]' >&2
  exit 2
fi
python3 - "$root" "${1:-}" <<'PY'
from pathlib import Path
import copy
import hashlib
import re
import sys
import yaml

if sys.flags.optimize:
    raise SystemExit("deployment validation requires assertions enabled")

root = Path(sys.argv[1])
rendered = Path(sys.argv[2]) if sys.argv[2] else None
base = root / "kubernetes/apps/google-sdp-evaluation"
resources = yaml.safe_load((base / "kustomization.yaml").read_text())["resources"]
assert set(resources) == {"namespace.yaml", "serviceaccount.yaml", "configmap.yaml", "job.yaml", "networkpolicy.yaml", "fqdnnetworkpolicy.yaml", "resourcequota.yaml", "limitrange.yaml"}
templates = [(base / name).read_text(encoding="utf-8") for name in resources]
combined = "\n".join(templates)
assert not re.search(r"(?i)(private.key|credentials.json|GOOGLE_APPLICATION_CREDENTIALS|LITELLM|kubectl apply|docker push|gcloud |secretKeyRef)", combined)
assert "REPLACE_WITH_PROJECT_ID" in combined and "REPLACE_WITH_GSA_EMAIL" in combined
assert "REPLACE_WITH_ARTIFACT_REGISTRY_DIGEST" in combined
assert not re.search(r"[a-z][a-z0-9-]+@[a-z][a-z0-9-]+\.iam\.gserviceaccount\.com", combined)
docs = list(yaml.safe_load_all(rendered.read_text(encoding="utf-8"))) if rendered else [yaml.safe_load(t) for t in templates]
assert len(docs) == 8
by_kind = {d["kind"]: d for d in docs}
assert set(by_kind) == {"Namespace", "ServiceAccount", "ConfigMap", "Job", "NetworkPolicy", "FQDNNetworkPolicy", "ResourceQuota", "LimitRange"}
assert by_kind["Namespace"]["metadata"]["name"] == "google-sdp-evaluation"
labels = by_kind["Namespace"]["metadata"]["labels"]
for level in ("enforce", "audit", "warn"):
    assert labels[f"pod-security.kubernetes.io/{level}"] == "restricted"
for doc in docs:
    assert doc["kind"] != "Secret"
    if doc["kind"] != "Namespace":
        assert doc["metadata"]["namespace"] == "google-sdp-evaluation"
sa = by_kind["ServiceAccount"]
assert sa["metadata"]["name"] == "google-sdp-evaluation" and sa["automountServiceAccountToken"] is True
annotation = sa["metadata"]["annotations"]["iam.gke.io/gcp-service-account"]
if rendered:
    assert re.fullmatch(r"google-sdp-runtime@[a-z][a-z0-9-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com", annotation)
else:
    assert annotation == "REPLACE_WITH_GSA_EMAIL"
config = by_kind["ConfigMap"]["data"]
assert config == {"region": "us-east1", "endpoint": "dlp.us-east1.rep.googleapis.com", "synthetic_corpus_path": "/app/evaluation/google-sdp/corpus.json"}
job = by_kind["Job"]["spec"]
assert job["suspend"] is True
assert job["backoffLimit"] == 0 and job["parallelism"] == job["completions"] == 1
assert 0 < job["activeDeadlineSeconds"] <= 900 and 0 < job["ttlSecondsAfterFinished"] <= 3600
pod = job["template"]["spec"]
assert pod["serviceAccountName"] == "google-sdp-evaluation" and pod["automountServiceAccountToken"] is True
assert pod["restartPolicy"] == "Never" and pod["enableServiceLinks"] is False
assert not any(k in pod for k in ("hostNetwork", "hostPID", "hostIPC", "hostPath"))
psc = pod["securityContext"]
assert psc["runAsNonRoot"] is True and psc["runAsUser"] == psc["runAsGroup"] == 65532
assert psc["seccompProfile"]["type"] == "RuntimeDefault"
assert len(pod["containers"]) == 1
container = pod["containers"][0]
assert container["args"] == ["--live"] and "ports" not in container
image = container["image"]
if rendered:
    match = re.fullmatch(r"us-east1-docker\.pkg\.dev/([a-z][a-z0-9-]{4,28}[a-z0-9])/[a-z][a-z0-9-]{0,62}/[a-z][a-z0-9._-]{0,127}@sha256:[0-9a-f]{64}", image)
    assert match and annotation.endswith(f"@{match.group(1)}.iam.gserviceaccount.com")
else:
    assert image == "REPLACE_WITH_ARTIFACT_REGISTRY_DIGEST"
env = {entry["name"]: entry.get("value") for entry in container["env"]}
assert env == {"PORTFOLIO_GOOGLE_SDP_PROJECT_ID": "REPLACE_WITH_PROJECT_ID" if not rendered else image.split("/")[1], "PORTFOLIO_GOOGLE_SDP_SYNTHETIC_ONLY_ACK": "I_ACKNOWLEDGE_SYNTHETIC_ONLY_GOOGLE_SDP_EVALUATION"}
csc = container["securityContext"]
assert csc["allowPrivilegeEscalation"] is False and csc["readOnlyRootFilesystem"] is True
assert csc["capabilities"]["drop"] == ["ALL"] and csc.get("privileged") is not True
for bound in ("requests", "limits"):
    assert set(container["resources"][bound]) == {"cpu", "memory", "ephemeral-storage"}
assert container["resources"]["requests"] == {"cpu": "100m", "memory": "128Mi", "ephemeral-storage": "64Mi"}
assert container["resources"]["limits"] == {"cpu": "500m", "memory": "512Mi", "ephemeral-storage": "256Mi"}
assert "volumes" not in pod and "volumeMounts" not in container
quota = by_kind["ResourceQuota"]["spec"]["hard"]
assert quota["pods"] == "1" and quota["count/jobs.batch"] == "1"
assert all(k in quota for k in ("requests.cpu", "limits.cpu", "requests.memory", "limits.memory", "requests.ephemeral-storage", "limits.ephemeral-storage"))
assert by_kind["LimitRange"]["spec"]["limits"][0]["type"] == "Container"
policy = by_kind["NetworkPolicy"]["spec"]
assert policy["podSelector"] == {} and set(policy["policyTypes"]) == {"Ingress", "Egress"}
assert not policy.get("ingress")
assert policy["egress"] == [
    {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}}, "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}}}], "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]},
    {"to": [{"ipBlock": {"cidr": "169.254.169.254/32"}}], "ports": [{"protocol": "TCP", "port": 80}]},
]
fqdn = by_kind["FQDNNetworkPolicy"]
assert fqdn["apiVersion"] == "networking.gke.io/v1alpha1"
assert fqdn["spec"] == {"podSelector": {}, "egress": [{"matches": [{"name": "dlp.us-east1.rep.googleapis.com"}], "ports": [{"protocol": "TCP", "port": 443}]}]}
assert fqdn["metadata"]["name"] == "google-sdp-evaluation-regional-egress"
for kind in ("FQDNNetworkPolicy", "NetworkPolicy"):
    assert by_kind[kind]["metadata"]["annotations"] == {"policy.network.gke.io/enable-logging": "true"}
assert by_kind["Namespace"]["metadata"]["annotations"] == {"policy.network.gke.io/enable-deny-logging": "true"}
logging = yaml.safe_load((base / "native-gke/networklogging.yaml").read_text())
assert logging == {"apiVersion": "networking.gke.io/v1alpha1", "kind": "NetworkLogging", "metadata": {"name": "default"}, "spec": {"cluster": {"allow": {"log": True, "delegate": True}, "deny": {"log": True, "delegate": True}}}}
if rendered:
    directory = rendered.parent
    assert list(yaml.safe_load_all((directory / "google-sdp-evaluation-controls.yaml").read_text())) == [d for d in docs if d["kind"] != "Job"]
    assert yaml.safe_load((directory / "google-sdp-evaluation-job.yaml").read_text()) == by_kind["Job"]
    assert yaml.safe_load((directory / "networklogging.yaml").read_text()) == logging
    preflight_docs = list(yaml.safe_load_all((directory / "google-sdp-egress-preflight.yaml").read_text()))
    assert len(preflight_docs) == 2
    cmap, preflight = preflight_docs
    probe_source = (root / "scripts/probe-google-sdp-egress.py").read_text(encoding="utf-8")
    assert cmap == {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "google-sdp-egress-preflight", "namespace": "google-sdp-evaluation"}, "immutable": True, "data": {"probe.py": probe_source}}
    expected = copy.deepcopy(by_kind["Job"])
    expected["metadata"]["name"] = "google-sdp-egress-preflight"
    expected["spec"].pop("suspend")
    expected["spec"].update(activeDeadlineSeconds=180, ttlSecondsAfterFinished=600)
    expected["spec"]["template"]["metadata"]["annotations"] = {"portfolio.example/probe-sha256": hashlib.sha256(probe_source.encode("utf-8")).hexdigest()}
    p = expected["spec"]["template"]["spec"]
    c = p["containers"][0]
    c.update(name="egress-preflight", command=["/usr/local/bin/python3.12", "/probe/probe.py"], args=["--network-preflight"])
    c["env"] = [{"name": "PORTFOLIO_GOOGLE_SDP_NETWORK_PREFLIGHT_ACK", "value": "I_ACKNOWLEDGE_SYNTHETIC_NETWORK_PREFLIGHT"}, {"name": "PORTFOLIO_GOOGLE_SDP_EXPECTED_GSA", "value": annotation}]
    c["volumeMounts"] = [{"name": "probe", "mountPath": "/probe", "readOnly": True}]
    p["volumes"] = [{"name": "probe", "configMap": {"name": "google-sdp-egress-preflight", "defaultMode": 0o444}}]
    assert preflight == expected
assert "NetworkPolicy cannot restrict" in combined
readme = (base / "README.md").read_text(encoding="utf-8")
assert "FQDN" in readme and "Presidio" in readme and "evaluation-only" in readme
for script in ("render-google-sdp-evaluation-job.sh", "validate-google-sdp-deployment.sh"):
    text = (root / "scripts" / script).read_text(encoding="utf-8")
    assert not re.search(r"(?m)^\s*(?:kubectl\s+apply|docker\s+push|gcloud\s+|cosign\s+sign)\b", text)
print("PASS: Google SDP evaluation deployment contract")
PY
