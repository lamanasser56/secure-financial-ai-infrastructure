"""Actual offline rendering/mutation and fixed harness-budget regressions."""

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

try:
    from google.cloud import dlp_v2
except ImportError:
    dlp_v2 = None

ROOT = Path(__file__).resolve().parents[2]
RENDERER = ROOT / "scripts/render-sdp-context-diagnostic-job.sh"
VALIDATOR = ROOT / "scripts/validate-sdp-context-diagnostic-deployment.py"
PROJECT = "synthetic-eval"
GSA = f"google-sdp-runtime@{PROJECT}.iam.gserviceaccount.com"
IMAGE = (
    f"us-east1-docker.pkg.dev/{PROJECT}/sdp-evaluation-images/"
    "google-sdp-context-diagnostic@sha256:" + "a" * 64
)
FILES = (
    "google-sdp-evaluation-controls.yaml",
    "google-sdp-evaluation-job.yaml",
    "google-sdp-egress-preflight.yaml",
    "networklogging.yaml",
)


class DiagnosticDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        completed = cls.render(PROJECT, GSA, IMAGE)
        if completed.returncode != 0:
            raise AssertionError(completed.stderr)
        cls.path = Path(next(
            line.removeprefix("Rendered manifest: ")
            for line in completed.stdout.splitlines()
            if line.startswith("Rendered manifest: ")
        ))
        cls.documents = list(yaml.safe_load_all(cls.path.read_text()))

    @classmethod
    def tearDownClass(cls):
        subprocess.run(
            ["bash", str(RENDERER), "--cleanup", str(cls.path.parent)],
            check=True, capture_output=True, cwd=ROOT,
        )

    @staticmethod
    def render(*arguments):
        return subprocess.run(
            ["bash", str(RENDERER), *arguments],
            capture_output=True, text=True, cwd=ROOT,
        )

    def validate_modified(self, mutate, side_mutation=None):
        documents = copy.deepcopy(self.documents)
        job = next(document for document in documents if document["kind"] == "Job")
        container = job["spec"]["template"]["spec"]["containers"][0]
        mutate(documents, job, container)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in FILES[2:]:
                shutil.copyfile(self.path.parent / name, directory / name)
            target = directory / "rendered.yaml"
            target.write_text(yaml.safe_dump_all(documents))
            (directory / FILES[0]).write_text(yaml.safe_dump_all([
                document for document in documents if document["kind"] != "Job"
            ]))
            (directory / FILES[1]).write_text(yaml.safe_dump(job))
            if side_mutation is not None:
                side_mutation(directory)
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(target)],
                cwd=ROOT, capture_output=True, text=True,
            )

    def test_exact_fixed_diagnostic_scope_and_inherited_security(self):
        self.assertEqual(self.validate_modified(lambda *_: None).returncode, 0)
        job = next(document for document in self.documents if document["kind"] == "Job")
        container = job["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(job["metadata"]["name"], "google-sdp-context-diagnostic")
        self.assertEqual(job["metadata"]["namespace"], "google-sdp-evaluation")
        self.assertEqual(container["args"], ["--live", "--diagnostic-first-case"])
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 120)
        self.assertTrue(job["spec"]["suspend"])
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        pod = job["spec"]["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "google-sdp-evaluation")
        self.assertEqual(pod["restartPolicy"], "Never")
        self.assertEqual(pod["securityContext"]["runAsUser"], 65532)
        self.assertEqual(pod["securityContext"]["runAsGroup"], 65532)
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(container["resources"]["limits"]["memory"], "512Mi")
        self.assertNotIn("volumes", pod)
        self.assertNotIn("ports", container)
        self.assertNotIn("Secret", [document["kind"] for document in self.documents])
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        for name in FILES:
            self.assertEqual((self.path.parent / name).stat().st_mode & 0o777, 0o600)

    def test_unapproved_inputs_and_extra_selectors_are_rejected(self):
        for arguments in (
            (PROJECT, GSA, IMAGE.replace("@sha256:" + "a" * 64, ":latest")),
            (PROJECT, GSA, IMAGE.replace("us-east1", "us-west1")),
            (PROJECT, GSA, IMAGE.replace("google-sdp-context-diagnostic@", "google-sdp-context@")),
            (PROJECT, GSA, IMAGE.replace("pkg.dev", "example.invalid")),
            (PROJECT, GSA, IMAGE.replace(PROJECT, "other-project")),
            (PROJECT, "invalid-gsa", IMAGE),
            (PROJECT, GSA.replace("google-sdp-runtime", "other-account"), IMAGE),
            (PROJECT, GSA.replace(PROJECT, "other-project"), IMAGE),
            ("/private/credentials.json", GSA, IMAGE),
            (PROJECT, GSA, "/private/key.json"),
            (PROJECT, GSA, IMAGE, "--case", "context-002"),
            (PROJECT, GSA, IMAGE, "--corpus", "/arbitrary"),
            (PROJECT, GSA, IMAGE, "--live"),
        ):
            with self.subTest(input_number=len(arguments), identity=arguments[0]):
                result = self.render(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Rendered manifest:", result.stdout)

    def test_missing_ack_full_campaign_and_execution_mutations_rejected(self):
        mutations = {
            "full_campaign": lambda d, j, c: c.update(args=["--live"]),
            "offline_only": lambda d, j, c: c.update(args=["--diagnostic-first-case"]),
            "arbitrary_case": lambda d, j, c: c["args"].extend(["--case", "context-002"]),
            "arbitrary_text": lambda d, j, c: c["args"].extend(["--text", "private"]),
            "arbitrary_file": lambda d, j, c: c["args"].extend(["--corpus", "/arbitrary"]),
            "missing_synthetic_ack": lambda d, j, c: c["env"].pop(1),
            "missing_diagnostic_ack": lambda d, j, c: c["env"].pop(2),
            "changed_ack": lambda d, j, c: c["env"][2].update(value="unapproved"),
            "duplicate_ack": lambda d, j, c: c["env"].append(dict(c["env"][2])),
            "credential_env": lambda d, j, c: c["env"].append({"name": "GOOGLE_APPLICATION_CREDENTIALS", "value": "/private/key.json"}),
            "command_override": lambda d, j, c: c.update(command=["/usr/local/bin/python3.12", "-c", "pass"]),
            "unsuspended": lambda d, j, c: j["spec"].update(suspend=False),
            "retry": lambda d, j, c: j["spec"].update(backoffLimit=1),
            "parallel": lambda d, j, c: j["spec"].update(parallelism=2),
            "deadline": lambda d, j, c: j["spec"].update(activeDeadlineSeconds=900),
            "default_ksa": lambda d, j, c: j["spec"]["template"]["spec"].update(serviceAccountName="default"),
            "production_namespace": lambda d, j, c: j["metadata"].update(namespace="production"),
            "privileged": lambda d, j, c: c["securityContext"].update(privileged=True),
            "unbounded_resource": lambda d, j, c: c["resources"].pop("limits"),
            "volume": lambda d, j, c: j["spec"]["template"]["spec"].update(volumes=[{"name": "arbitrary", "emptyDir": {}}]),
            "port": lambda d, j, c: c.update(ports=[{"containerPort": 8080}]),
            "mutable_image": lambda d, j, c: c.update(image=IMAGE.replace("@sha256:" + "a" * 64, ":latest")),
            "scope_annotation": lambda d, j, c: j["metadata"]["annotations"].update({"portfolio.example/evaluation-scope": "campaign"}),
            "attempt_annotation": lambda d, j, c: j["metadata"]["annotations"].update({"portfolio.example/content-attempt-limit": "172"}),
            "corpus": lambda d, j, c: next(x for x in d if x["kind"] == "ConfigMap")["data"].update(synthetic_corpus_path="/arbitrary"),
            "endpoint": lambda d, j, c: next(x for x in d if x["kind"] == "ConfigMap")["data"].update(endpoint="dlp.googleapis.com"),
            "unrestricted_egress": lambda d, j, c: next(x for x in d if x["kind"] == "NetworkPolicy")["spec"].update(egress=[{}]),
            "added_secret": lambda d, j, c: d.append({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "credential"}}),
        }
        for name, mutation in mutations.items():
            with self.subTest(mutation=name):
                result = self.validate_modified(mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stderr.strip(), "diagnostic deployment contract rejected")

    def test_divergent_apply_subject_and_symlink_are_rejected(self):
        def diverge(directory):
            job = yaml.safe_load((directory / FILES[1]).read_text())
            job["spec"]["suspend"] = False
            (directory / FILES[1]).write_text(yaml.safe_dump(job))

        self.assertNotEqual(self.validate_modified(lambda *_: None, diverge).returncode, 0)

        def symlink(directory):
            (directory / FILES[3]).unlink()
            (directory / FILES[3]).symlink_to(self.path.parent / FILES[3])

        self.assertNotEqual(self.validate_modified(lambda *_: None, symlink).returncode, 0)

    def test_first_case_offline_harness_has_no_external_calls(self):
        result = subprocess.run(
            [sys.executable, "scripts/evaluate-sdp-context-policy.py", "--diagnostic-first-case"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["scope"], "context_001_diagnostic_only")
        self.assertEqual([case["case_id"] for case in report["cases"]], ["context-001"])
        self.assertEqual(report["sdk_attempts"], 0)
        self.assertEqual(report["injected_attempts"], 0)
        self.assertEqual(report["outcome"], "OFFLINE_REFERENCE_PASS_GOOGLE_UNPROVEN")
        self.assertFalse(report["authority_changed"])

    def test_cli_arbitrary_selectors_rejected_before_harness(self):
        for selectors in (["--case", "context-002"], ["--text", "private"], ["--corpus", "/arbitrary"]):
            result = subprocess.run(
                [sys.executable, "scripts/evaluate-sdp-context-policy.py", "--diagnostic-first-case", *selectors],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")

    def test_source_limits_and_retry_controls_remain_the_existing_contract(self):
        from runtime.phase3 import google_sdp_adapter as adapter

        spec = importlib.util.spec_from_file_location(
            "diagnostic_contract_harness", ROOT / "scripts/evaluate-sdp-context-policy.py"
        )
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        self.assertEqual(adapter.MAX_INPUT_BYTES, 4096)
        self.assertEqual(adapter.MAX_OUTPUT_BYTES, 4096)
        self.assertEqual(adapter.RPC_TIMEOUT_SECONDS, 3)
        self.assertEqual(adapter.OVERALL_TIMEOUT_SECONDS, 8)
        self.assertEqual(runner.DIAGNOSTIC_SECONDS, 30)
        # First-case execution creates a real shared admission budget of two,
        # measured by interception before transport creation, without any RPC.
        from unittest.mock import patch

        observed = []
        original_budget = runner.ContentAttemptBudget

        def budget(limit):
            observed.append(limit)
            return original_budget(limit)

        with patch.object(runner, "ContentAttemptBudget", side_effect=budget):
            runner.evaluate(first_case_only=True)
        self.assertEqual(observed, [2])

    def test_renderer_cleanup_rejects_nonowned_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.render("--cleanup", temporary)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(Path(temporary).is_dir())

    @unittest.skipIf(dlp_v2 is None, "mandatory separate locked SDK diagnostic gate")
    def test_fixed_first_case_uses_only_two_injected_sdk_envelopes_and_no_retries(self):
        from runtime.phase3 import google_sdp_adapter as adapter

        spec = importlib.util.spec_from_file_location(
            "diagnostic_transport_harness", ROOT / "scripts/evaluate-sdp-context-policy.py"
        )
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        case = runner.load_corpus()["cases"][0]
        self.assertEqual(case["case_id"], "context-001")
        text = case["text"]
        spans = case["expected_spans"]
        inspected = dlp_v2.InspectContentResponse(result={
            "findings_truncated": False,
            "findings": [
                {
                    "info_type": {"name": span["info_type"]},
                    "location": {
                        "codepoint_range": {"start": span["start"], "end": span["end"]},
                        "byte_range": {
                            "start": len(text[:span["start"]].encode()),
                            "end": len(text[:span["end"]].encode()),
                        },
                    },
                }
                for span in spans
            ],
        })
        cursor, output, groups = 0, [], {}
        for span in spans:
            start, end, name = span["start"], span["end"], span["info_type"]
            output.extend((text[cursor:start], "[" + name + "]"))
            cursor = end
            count, size = groups.get(name, (0, 0))
            groups[name] = (count + 1, size + len(text[start:end].encode()))
        output.append(text[cursor:])
        transformed = dlp_v2.DeidentifyContentResponse(
            item={"value": "".join(output)},
            overview={
                "transformed_bytes": sum(size for _, size in groups.values()),
                "transformation_summaries": [
                    {
                        "info_type": {"name": name},
                        "transformed_bytes": size,
                        "transformation": {"replace_with_info_type_config": {}},
                        "results": [{"count": count, "code": "SUCCESS"}],
                    }
                    for name, (count, size) in groups.items()
                ],
            },
        )
        events = []

        class InjectedTransport:
            api_endpoint = adapter.ENDPOINT

            def inspect_content(self, *, request, retry, timeout):
                dlp_v2.InspectContentRequest(request)
                events.append(("inspect", retry, timeout))
                return inspected

            def deidentify_content(self, *, request, retry, timeout):
                dlp_v2.DeidentifyContentRequest(request)
                events.append(("deidentify", retry, timeout))
                return transformed

        report = runner.evaluate(client=InjectedTransport(), first_case_only=True)
        self.assertEqual([event[0] for event in events], ["inspect", "deidentify"])
        self.assertTrue(all(retry is None and 0 < timeout <= 3 for _, retry, timeout in events))
        self.assertEqual(report["scope"], "context_001_diagnostic_only")
        self.assertEqual(report["sdk_attempts"], 0)
        self.assertEqual(report["injected_attempts"], 2)
        self.assertEqual(report["required_pass"], 1)
        self.assertEqual(report["unexecuted"], 0)
        self.assertEqual(report["google_quality"], "unmeasured")
        self.assertEqual([value["case_id"] for value in report["cases"]], ["context-001"])


if __name__ == "__main__":
    unittest.main()
