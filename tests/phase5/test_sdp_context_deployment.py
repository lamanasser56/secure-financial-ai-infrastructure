"""Real offline render/mutation checks; no cloud operation or registry access."""

from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "synthetic-eval"


class ContextDeploymentTests(unittest.TestCase):
    def render(self, image):
        return subprocess.run(
            [
                "bash",
                "scripts/render-sdp-context-job.sh",
                PROJECT,
                f"google-sdp-runtime@{PROJECT}.iam.gserviceaccount.com",
                image,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_context_profile_preserves_dispatch_only_and_pre_auth_qualification(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/release-google-sdp-evaluation.yml").read_text()
        )
        trigger = workflow.get("on", workflow.get(True))
        profile = trigger["workflow_dispatch"]["inputs"]["evaluation_profile"]
        self.assertEqual(profile["options"], ["seed", "context-pattern-v1", "context-001-diagnostic-v1"])
        self.assertEqual(profile["default"], "seed")
        for name in ("qualify", "publish"):
            steps = workflow["jobs"][name]["steps"]
            preauth = next(
                v["run"] for v in steps if "APPROVED_COMMIT" in v.get("env", {})
            )
            self.assertIn('[[ "$IMAGE_NAME" == google-sdp-context', preauth)
        helper = (ROOT / "scripts/qualify-sdp-context-release.sh").read_text()
        self.assertLess(
            helper.index("source_input_sha256"),
            helper.index("bash scripts/build-sdp-context-image.sh"),
        )
        self.assertIn('[[ "$configuration" ==', helper)
        self.assertIn("--network none", helper)
        self.assertNotIn("docker push", helper)
        self.assertNotIn("cosign sign", helper)

    def test_exact_context_digest_render_security_and_rejection_mutations(self):
        image = (
            "us-east1-docker.pkg.dev/synthetic-eval/sdp-evaluation-images/google-sdp-context@sha256:"
            + "a" * 64
        )
        result = self.render(image)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = Path(
            next(
                v.removeprefix("Rendered manifest: ")
                for v in result.stdout.splitlines()
                if v.startswith("Rendered manifest: ")
            )
        )
        try:
            docs = list(yaml.safe_load_all(path.read_text()))
            job = next(v for v in docs if v["kind"] == "Job")
            self.assertTrue(job["spec"]["suspend"])
            self.assertEqual(
                job["spec"]["template"]["spec"]["serviceAccountName"],
                "google-sdp-evaluation",
            )
            for mutation in (
                "namespace",
                "serviceaccount",
                "image",
                "ack",
                "extraenv",
                "privilege",
                "corpus",
                "command",
                "initcontainer",
                "volume",
                "diagnostic",
                "deadline",
                "retry",
                "parallelism",
                "secondack",
            ):
                altered = yaml.safe_load_all(path.read_text())
                altered = list(altered)
                j = next(v for v in altered if v["kind"] == "Job")
                c = j["spec"]["template"]["spec"]["containers"][0]
                if mutation == "namespace":
                    j["metadata"]["namespace"] = "production"
                if mutation == "serviceaccount":
                    j["spec"]["template"]["spec"]["serviceAccountName"] = "default"
                if mutation == "image":
                    c["image"] = image.replace("@sha256:" + "a" * 64, ":latest")
                if mutation == "ack":
                    c["env"] = [
                        e
                        for e in c["env"]
                        if not e["name"].startswith("PORTFOLIO_SDP_CONTEXT")
                    ]
                if mutation == "extraenv":
                    c["env"].append(
                        {
                            "name": "GOOGLE_APPLICATION_CREDENTIALS",
                            "value": "/private/key.json",
                        }
                    )
                if mutation == "privilege":
                    c["securityContext"]["allowPrivilegeEscalation"] = True
                if mutation == "corpus":
                    c["args"] = ["--live", "--corpus", "/arbitrary"]
                if mutation == "command":
                    c["command"] = ["/usr/local/bin/python3.12", "-c", "pass"]
                if mutation == "initcontainer":
                    j["spec"]["template"]["spec"]["initContainers"] = [dict(c)]
                if mutation == "volume":
                    j["spec"]["template"]["spec"]["volumes"] = [
                        {"name": "arbitrary", "emptyDir": {}}
                    ]
                if mutation == "diagnostic":
                    c["args"] = ["--live", "--diagnostic-first-case"]
                if mutation == "deadline":
                    j["spec"]["activeDeadlineSeconds"] = 120
                if mutation == "retry":
                    j["spec"]["backoffLimit"] = 1
                if mutation == "parallelism":
                    j["spec"]["parallelism"] = 2
                if mutation == "secondack":
                    c["env"].append({"name": "PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK",
                                     "value": "I_ACKNOWLEDGE_CONTEXT_001_ONLY_TWO_ATTEMPTS"})
                with tempfile.TemporaryDirectory() as temporary:
                    target = Path(temporary)
                    for name in (
                        "networklogging.yaml",
                        "google-sdp-egress-preflight.yaml",
                    ):
                        shutil.copyfile(path.parent / name, target / name)
                    invalid = target / "invalid.yaml"
                    invalid.write_text(yaml.safe_dump_all(altered))
                    (target / "google-sdp-evaluation-controls.yaml").write_text(
                        yaml.safe_dump_all([v for v in altered if v["kind"] != "Job"])
                    )
                    (target / "google-sdp-evaluation-job.yaml").write_text(
                        yaml.safe_dump(j)
                    )
                    probe = subprocess.run(
                        [
                            "python3",
                            "scripts/validate-sdp-context-job.py",
                            str(invalid),
                        ],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(probe.returncode, 0, mutation)
            for invalid in (
                image.replace("@sha256:" + "a" * 64, ":latest"),
                image.replace("us-east1", "us-west1"),
                image.replace("google-sdp-context@", "google-sdp-evaluation@"),
            ):
                self.assertNotEqual(self.render(invalid).returncode, 0)
        finally:
            subprocess.run(
                [
                    "bash",
                    "scripts/render-sdp-context-job.sh",
                    "--cleanup",
                    str(path.parent),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )
