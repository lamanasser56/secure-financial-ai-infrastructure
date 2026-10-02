"""Offline contracts for the unapplied synthetic Google SDP release package."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/release-google-sdp-evaluation.yml"
PACKAGE = ROOT / "kubernetes/apps/google-sdp-evaluation"
RENDER = ROOT / "scripts/render-google-sdp-evaluation-job.sh"
VALIDATE = ROOT / "scripts/validate-google-sdp-deployment.sh"
PROJECT = "synthetic-eval-123"
GSA = f"sdp-evaluation@{PROJECT}.iam.gserviceaccount.com"
DIGEST = f"me-central2-docker.pkg.dev/{PROJECT}/synthetic-repo/evaluation@sha256:" + "a" * 64


def render(project=PROJECT, gsa=GSA, digest=DIGEST):
    return subprocess.run(
        ["bash", str(RENDER), project, gsa, digest],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )


class DeploymentContractTests(unittest.TestCase):
    def test_templates_validate_offline(self):
        result = subprocess.run(["bash", str(VALIDATE)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_workflow_manual_only_pinned_and_least_privilege(self):
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        triggers = workflow.get("on", workflow.get(True))
        self.assertEqual(set(triggers), {"workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {})
        self.assertEqual(workflow["jobs"]["qualify"]["permissions"], {"contents": "read"})
        self.assertEqual(workflow["jobs"]["publish"]["permissions"], {"contents": "read", "id-token": "write"})
        self.assertEqual(workflow["jobs"]["publish"]["needs"], "qualify")
        for job in workflow["jobs"].values():
            self.assertLessEqual(job["timeout-minutes"], 45)
            for step in job["steps"]:
                if "uses" in step:
                    self.assertRegex(step["uses"], r"^[\w-]+/[\w-]+@[0-9a-f]{40}$")
        self.assertEqual(set(triggers["workflow_dispatch"]["inputs"]), {"source_commit", "region", "artifact_repository", "image_name"})

    def test_workflow_gate_order_and_digest_signing(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertLess(text.index("PORTFOLIO_CHECK_GOOGLE_SDP_LOCK=1"), text.index("google-github-actions/auth@"))
        self.assertLess(text.index("evaluate-container-vulnerability-policy.py"), text.index("google-github-actions/auth@"))
        self.assertLess(text.index("QUALIFIED_IMAGE_ID"), text.index("google-github-actions/auth@"))
        self.assertLess(text.index("docker push"), text.index("cosign sign"))
        self.assertLess(text.rindex("evaluate-container-vulnerability-policy.py"), text.index("cosign sign"))
        self.assertIn("dockerConfig", text)
        self.assertIn("immutableTags", text)
        self.assertIn("docker buildx imagetools inspect --raw", text)
        self.assertIn('python scripts/google-sdp-image-config-id.py "$RUNNER_TEMP/pulled-image.tar"', text)
        self.assertEqual(text.count("s/^Image configuration ID: //p"), 2)
        self.assertIn('cosign sign --yes "$DIGEST_REF"', text)
        self.assertIn('cosign verify --certificate-identity', text)
        self.assertIn('"$DIGEST_REF" > "$RUNNER_TEMP/release-evidence/cosign-verification.json"', text)
        self.assertIn("create_credentials_file: false", text)
        self.assertEqual(text.count('[[ "$GITHUB_RUN_ATTEMPT" == 1 ]]'), 2)
        self.assertIn("workload_identity_provider:", text)
        self.assertNotRegex(text, r"credentials_json:|service_account_key|kubectl apply|gcloud compute|--push\b|dlp\.projects")
        self.assertIn("me-central2", text)

    def test_render_exact_digest_and_cleanup(self):
        result = render()
        self.assertEqual(result.returncode, 0, result.stderr)
        match = re.search(r"Rendered manifest: (\S+)", result.stdout)
        self.assertIsNotNone(match)
        manifest = Path(match.group(1))
        try:
            self.assertTrue(manifest.exists())
            documents = {doc["kind"]: doc for doc in yaml.safe_load_all(manifest.read_text())}
            self.assertEqual(documents["Job"]["spec"]["template"]["spec"]["containers"][0]["image"], DIGEST)
            self.assertEqual(documents["ServiceAccount"]["metadata"]["annotations"]["iam.gke.io/gcp-service-account"], GSA)
            validated = subprocess.run(["bash", str(VALIDATE), str(manifest)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(validated.returncode, 0, validated.stderr)
        finally:
            cleanup = subprocess.run(["bash", str(RENDER), "--cleanup", str(manifest.parent)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(cleanup.returncode, 0, cleanup.stderr)
        self.assertFalse(manifest.parent.exists())

    def test_invalid_render_inputs_fail_closed(self):
        cases = [
            ("bad/project", GSA, DIGEST),
            (PROJECT, "x@example.com", DIGEST),
            (PROJECT, "sdp-evaluation@" + "other-project-123" + ".iam.gserviceaccount.com", DIGEST),
            (PROJECT, GSA, DIGEST.split("@sha256:")[0] + ":latest"),
            (PROJECT, GSA, DIGEST.replace("me-central2-docker.pkg.dev", "us-docker.pkg.dev")),
            (PROJECT, GSA, DIGEST.replace(PROJECT, "other-project-123")),
            (PROJECT, GSA, "docker.io/example/evaluation@sha256:" + "a" * 64),
            (PROJECT, GSA, "credentials.json"),
        ]
        for values in cases:
            with self.subTest(values=values):
                self.assertNotEqual(render(*values).returncode, 0)

    def test_validator_rejects_mutated_render(self):
        result = render()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = Path(re.search(r"Rendered manifest: (\S+)", result.stdout).group(1))
        original = list(yaml.safe_load_all(manifest.read_text()))
        try:
            for mutation in ("default_service_account", "privileged", "open_egress", "secret"):
                with self.subTest(mutation=mutation):
                    documents = list(yaml.safe_load_all(yaml.safe_dump_all(original)))
                    by_kind = {document["kind"]: document for document in documents}
                    if mutation == "default_service_account":
                        by_kind["Job"]["spec"]["template"]["spec"]["serviceAccountName"] = "default"
                    elif mutation == "privileged":
                        by_kind["Job"]["spec"]["template"]["spec"]["containers"][0]["securityContext"]["privileged"] = True
                    elif mutation == "open_egress":
                        by_kind["NetworkPolicy"]["spec"]["egress"].append({"to": [{"ipBlock": {"cidr": "0.0.0.0/0"}}]})
                    else:
                        documents.append({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "unexpected", "namespace": "google-sdp-evaluation"}})
                    manifest.write_text(yaml.safe_dump_all(documents))
                    checked = subprocess.run(["bash", str(VALIDATE), str(manifest)], cwd=ROOT, capture_output=True, text=True)
                    self.assertNotEqual(checked.returncode, 0)
        finally:
            subprocess.run(["bash", str(RENDER), "--cleanup", str(manifest.parent)], cwd=ROOT, check=True, capture_output=True, text=True)

    def test_isolated_job_and_network_boundaries(self):
        resources = yaml.safe_load((PACKAGE / "kustomization.yaml").read_text())["resources"]
        docs = {item["kind"]: item for name in resources for item in yaml.safe_load_all((PACKAGE / name).read_text())}
        self.assertEqual(docs["Namespace"]["metadata"]["name"], "google-sdp-evaluation")
        self.assertNotIn("Secret", docs)
        self.assertNotIn("Role", docs)
        self.assertNotIn("RoleBinding", docs)
        job = docs["Job"]["spec"]
        self.assertEqual(job["backoffLimit"], 0)
        self.assertLessEqual(job["activeDeadlineSeconds"], 900)
        self.assertLessEqual(job["ttlSecondsAfterFinished"], 3600)
        pod = job["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "google-sdp-evaluation")
        self.assertEqual(pod["securityContext"]["runAsUser"], 65532)
        self.assertEqual(pod["securityContext"]["seccompProfile"]["type"], "RuntimeDefault")
        container = pod["containers"][0]
        self.assertEqual(container["args"], ["--live"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertNotIn("ports", container)
        self.assertEqual(docs["NetworkPolicy"]["spec"]["podSelector"], {})
        self.assertNotIn("ingress", docs["NetworkPolicy"]["spec"])
        for rule in docs["NetworkPolicy"]["spec"]["egress"]:
            self.assertIn("ports", rule)
        self.assertEqual(docs["ConfigMap"]["data"]["region"], "me-central2")
        self.assertEqual(docs["ConfigMap"]["data"]["endpoint"], "dlp.me-central2.rep.googleapis.com")

    def test_no_project_credentials_or_mutating_commands_in_package(self):
        source = "\n".join(path.read_text() for path in PACKAGE.glob("*.yaml"))
        self.assertIn("REPLACE_WITH_PROJECT_ID", source)
        self.assertIn("REPLACE_WITH_GSA_EMAIL", source)
        self.assertNotRegex(source, r"[a-z][a-z0-9-]+@[a-z][a-z0-9-]+\.iam\.gserviceaccount\.com")
        for script in (RENDER, VALIDATE):
            self.assertNotRegex(script.read_text(), r"(?m)^\s*(?:kubectl\s+apply|docker\s+push|gcloud\s+|cosign\s+sign)\b")
        readme = (PACKAGE / "README.md").read_text()
        self.assertIn("FQDN", readme)
        self.assertIn("Presidio remains authoritative", readme)
        self.assertIn("evaluation-only", readme)


if __name__ == "__main__":
    unittest.main()
