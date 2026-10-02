#!/usr/bin/env bash
set -Eeuo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
if (($# > 1)); then
  echo 'usage: validate-google-sdp-deployment.sh [RENDERED_MANIFEST]' >&2
  exit 2
fi
python3 - "$root" "${1:-}" <<'PY'
from pathlib import Path
import re
import sys
import yaml

if sys.flags.optimize:
    raise SystemExit("deployment validation requires assertions enabled")

root = Path(sys.argv[1])
rendered = Path(sys.argv[2]) if sys.argv[2] else None
base = root / "kubernetes/apps/google-sdp-evaluation"
resources = yaml.safe_load((base / "kustomization.yaml").read_text())["resources"]
assert set(resources) == {"namespace.yaml", "serviceaccount.yaml", "configmap.yaml", "job.yaml", "networkpolicy.yaml", "resourcequota.yaml", "limitrange.yaml"}
templates = [(base / name).read_text(encoding="utf-8") for name in resources]
combined = "\n".join(templates)
assert not re.search(r"(?i)(private.key|credentials.json|GOOGLE_APPLICATION_CREDENTIALS|LITELLM|kubectl apply|docker push|gcloud |secretKeyRef)", combined)
assert "REPLACE_WITH_PROJECT_ID" in combined and "REPLACE_WITH_GSA_EMAIL" in combined
assert "REPLACE_WITH_ARTIFACT_REGISTRY_DIGEST" in combined
assert not re.search(r"[a-z][a-z0-9-]+@[a-z][a-z0-9-]+\.iam\.gserviceaccount\.com", combined)
docs = list(yaml.safe_load_all(rendered.read_text(encoding="utf-8"))) if rendered else [yaml.safe_load(t) for t in templates]
assert len(docs) == 7
by_kind = {d["kind"]: d for d in docs}
assert set(by_kind) == {"Namespace", "ServiceAccount", "ConfigMap", "Job", "NetworkPolicy", "ResourceQuota", "LimitRange"}
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
    assert re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com", annotation)
else:
    assert annotation == "REPLACE_WITH_GSA_EMAIL"
config = by_kind["ConfigMap"]["data"]
assert config == {"region": "me-central2", "endpoint": "dlp.me-central2.rep.googleapis.com", "synthetic_corpus_path": "/app/evaluation/google-sdp/corpus.json"}
job = by_kind["Job"]["spec"]
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
    match = re.fullmatch(r"me-central2-docker\.pkg\.dev/([a-z][a-z0-9-]{4,28}[a-z0-9])/[a-z][a-z0-9-]{0,62}/[a-z][a-z0-9._-]{0,127}@sha256:[0-9a-f]{64}", image)
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
for rule in policy["egress"]:
    assert rule.get("to") and rule.get("ports")
    assert all(p.get("protocol") in {"TCP", "UDP"} and isinstance(p.get("port"), int) for p in rule["ports"])
    for destination in rule["to"]:
        if "ipBlock" in destination and destination["ipBlock"]["cidr"] == "0.0.0.0/0":
            assert rule["ports"] == [{"protocol": "TCP", "port": 443}]
            assert set(destination["ipBlock"]["except"]) == {"10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4"}
assert "NetworkPolicy cannot restrict" in combined
readme = (base / "README.md").read_text(encoding="utf-8")
assert "FQDN" in readme and "Presidio" in readme and "evaluation-only" in readme
for script in ("render-google-sdp-evaluation-job.sh", "validate-google-sdp-deployment.sh"):
    text = (root / "scripts" / script).read_text(encoding="utf-8")
    assert not re.search(r"(?m)^\s*(?:kubectl\s+apply|docker\s+push|gcloud\s+|cosign\s+sign)\b", text)
print("PASS: Google SDP evaluation deployment contract")
PY
