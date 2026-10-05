"""Actual offline rendering and adversarial admission; never apply a resource."""
import copy
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "synthetic-eval"
IMAGE = "us-east1-docker.pkg.dev/synthetic-eval/sdp-evaluation-images/google-sdp-context@sha256:667ceec4b8290df1341a91a7685ad140319fca6d23f92b9948dddf9fac64136b"


class EmailDiagnosticDeploymentTests(unittest.TestCase):
    def render(self, image=IMAGE, extra=()):
        return subprocess.run([
            "bash", "scripts/render-sdp-email-diagnostic-job.sh", PROJECT,
            f"google-sdp-runtime@{PROJECT}.iam.gserviceaccount.com", image, *extra,
        ], cwd=ROOT, capture_output=True, text=True)

    def test_exact_program_image_controls_and_mutation_rejections(self):
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("maximum eight", result.stdout)
        path = Path(next(line.removeprefix("Rendered manifest: ") for line in result.stdout.splitlines() if line.startswith("Rendered manifest: ")))
        try:
            documents = list(yaml.safe_load_all(path.read_text()))
            job = next(d for d in documents if d["kind"] == "Job")
            container = job["spec"]["template"]["spec"]["containers"][0]
            code = (ROOT / "scripts/diagnose-sdp-email-context.py").read_text()
            self.assertEqual(container["args"], ["-c", code, "--live"])
            self.assertEqual(container["command"], ["/usr/local/bin/python3.12"])
            self.assertEqual(container["image"], IMAGE)
            self.assertEqual(job["metadata"]["annotations"]["portfolio.example/program-sha256"], hashlib.sha256(code.encode()).hexdigest())
            self.assertEqual(job["spec"]["activeDeadlineSeconds"], 120)
            self.assertEqual(job["spec"]["backoffLimit"], 0)
            self.assertTrue(job["spec"]["suspend"])
            self.assertNotIn("volumes", job["spec"]["template"]["spec"])
            for mutation in (
                "campaign", "firstcase", "case", "code", "command", "ack", "extraack", "credential",
                "endpoint", "proxy", "image", "deadline", "retry", "parallelism", "unsuspend",
                "namespace", "serviceaccount", "volume", "privilege", "region", "scope", "programhash",
            ):
                with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                    altered = copy.deepcopy(documents)
                    j = next(d for d in altered if d["kind"] == "Job")
                    pod = j["spec"]["template"]["spec"]
                    c = pod["containers"][0]
                    if mutation == "campaign": c["args"] = ["--live"]
                    if mutation == "firstcase": c["args"] = ["--live", "--diagnostic-first-case"]
                    if mutation == "case": c["args"] += ["--case", "context-061"]
                    if mutation == "code": c["args"][1] += "\nprint('changed')\n"
                    if mutation == "command": c["command"] = ["sh", "-c"]
                    if mutation == "ack": c["env"] = c["env"][:-1]
                    if mutation == "extraack": c["env"].append({"name": "PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK", "value": "I_ACKNOWLEDGE_CONTEXT_001_ONLY_TWO_ATTEMPTS"})
                    if mutation == "credential": c["env"].append({"name": "GOOGLE_APPLICATION_CREDENTIALS", "value": "/private/key.json"})
                    if mutation == "endpoint": c["env"].append({"name": "PORTFOLIO_GOOGLE_SDP_ENDPOINT", "value": "other.invalid"})
                    if mutation == "proxy": c["env"].append({"name": "HTTPS_PROXY", "value": "https://other.invalid"})
                    if mutation == "image": c["image"] = IMAGE[:-1] + "a"
                    if mutation == "deadline": j["spec"]["activeDeadlineSeconds"] = 900
                    if mutation == "retry": j["spec"]["backoffLimit"] = 1
                    if mutation == "parallelism": j["spec"]["parallelism"] = 2
                    if mutation == "unsuspend": j["spec"]["suspend"] = False
                    if mutation == "namespace": j["metadata"]["namespace"] = "production"
                    if mutation == "serviceaccount": pod["serviceAccountName"] = "default"
                    if mutation == "volume": pod["volumes"] = [{"name": "raw", "hostPath": {"path": "/tmp"}}]
                    if mutation == "privilege": c["securityContext"]["allowPrivilegeEscalation"] = True
                    if mutation == "region": next(d for d in altered if d["kind"] == "ConfigMap")["data"]["region"] = "us-west1"
                    if mutation == "scope": j["metadata"]["annotations"]["portfolio.example/evaluation-scope"] = "full-campaign"
                    if mutation == "programhash": j["metadata"]["annotations"]["portfolio.example/program-sha256"] = "0" * 64
                    target = Path(temporary)
                    for name in ("networklogging.yaml", "google-sdp-egress-preflight.yaml"):
                        shutil.copyfile(path.parent / name, target / name)
                    (target / "invalid.yaml").write_text(yaml.safe_dump_all(altered))
                    (target / "google-sdp-evaluation-controls.yaml").write_text(yaml.safe_dump_all([d for d in altered if d["kind"] != "Job"]))
                    (target / "google-sdp-evaluation-job.yaml").write_text(yaml.safe_dump(j))
                    probe = subprocess.run([sys.executable, "scripts/validate-sdp-email-diagnostic-deployment.py", str(target / "invalid.yaml")], cwd=ROOT, capture_output=True)
                    self.assertNotEqual(probe.returncode, 0)
        finally:
            subprocess.run(["bash", "scripts/render-sdp-email-diagnostic-job.sh", "--cleanup", str(path.parent)], cwd=ROOT, check=True, capture_output=True)

    def test_unapproved_image_and_selectors_rejected_before_render(self):
        for image in (IMAGE[:-1] + "a", IMAGE.replace("us-east1", "us-west1"), IMAGE.split("@sha256:")[0] + ":latest", IMAGE.replace("google-sdp-context@", "google-sdp-context-diagnostic@")):
            self.assertNotEqual(self.render(image).returncode, 0)
        self.assertNotEqual(self.render(extra=("--case", "context-060")).returncode, 0)

    def test_duplicate_yaml_keys_and_special_files_are_rejected(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("email_validator", ROOT / "scripts/validate-sdp-email-diagnostic-deployment.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "duplicate.yaml"
            target.write_text("kind: Job\nkind: ConfigMap\n")
            with self.assertRaises(ValueError): module.read_yaml(target)
            link = Path(temporary) / "link.yaml"
            link.symlink_to(target)
            with self.assertRaises(ValueError): module.read_yaml(link)
            target.write_bytes(b"x" * 131073)
            with self.assertRaises(ValueError): module.read_yaml(target)


if __name__ == "__main__":
    unittest.main()
