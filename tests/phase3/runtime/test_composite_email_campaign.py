"""Offline AM-R4 composite campaign contracts; injected providers are simulations only.

Nothing here is Google detection evidence. Google-only records, policy, corpus and
the SDP image inputs stay unchanged; the composite scope never claims Google quality.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest

from runtime.phase3 import google_sdp_adapter as adapter
from runtime.phase3.sdp_context_policy import load_policy, reference_spans
from test_google_sdp_adapter import output

ROOT = Path(__file__).resolve().parents[3]
IMAGE_FILES = ["scripts/evaluate-sdp-context-policy.py", "runtime/phase3/__init__.py", "runtime/phase3/google_sdp_adapter.py",
               "runtime/phase3/sdp_context_policy.py", "runtime/phase3/trusted_runtime.py", "evaluation/google-sdp/deployment.json",
               "evaluation/google-sdp-context/policy.json", "evaluation/google-sdp-context/corpus.json",
               "evaluation/google-sdp-context/corpus.schema.json", "evaluation/google-sdp-context/result.schema.json"]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROGRAM = load("composite_program", "scripts/evaluate-composite-email-campaign.py")
VALIDATOR = load("composite_validator", "scripts/validate-composite-email-campaign-result.py")
GOOGLE_VALIDATOR = load("google_validator", "scripts/validate-sdp-context-campaign-result.py")


def provider_findings(text, drop=()):
    mapping = load_policy()["mapping"]
    findings, pieces, cursor = [], [], 0
    for start, end, name in reference_spans(text):
        if name in drop:
            continue
        findings.append(NS(info_type=NS(name=name), location=NS(
            codepoint_range=NS(start=start, end=end),
            byte_range=NS(start=len(text[:start].encode()), end=len(text[:end].encode())))))
        pieces.extend((text[cursor:start], name))
        cursor = end
    pieces.append(text[cursor:])
    return findings, "".join(pieces)


class SimulatedGoogle:
    """Answers each request from the local reference on the text it actually receives."""
    api_endpoint = adapter.ENDPOINT

    def __init__(self, drop=()):
        self.drop, self.received = drop, []

    def inspect_content(self, *, request, retry, timeout):
        text = request["item"]["value"]
        self.received.append(text)
        return NS(result=NS(findings=provider_findings(text, self.drop)[0], findings_truncated=False))

    def deidentify_content(self, *, request, retry, timeout):
        text = request["item"]["value"]
        findings, replaced = provider_findings(text, self.drop)
        return output(replaced, findings, text)


class CompositeCampaign(unittest.TestCase):
    def test_offline_reference_passes_by_category(self):
        result = PROGRAM.evaluate(False)
        self.assertEqual((result["required_pass"], result["required_fail"], result["observations"], result["unexecuted"],
                          result["deterministic_email_cases"], result["sdk_attempts"], result["outcome"]),
                         (70, 0, 16, 0, 3, 0, "OFFLINE_COMPOSITE_REFERENCE_PASS_PROVIDER_UNPROVEN"))
        self.assertIs(result["google_qualification_claimed"], False)
        self.assertEqual(VALIDATOR.validate(self.write(result))["outcome"], result["outcome"])

    def test_provider_never_receives_plain_addresses_and_injected_attempts_are_counted(self):
        client = SimulatedGoogle()
        result = PROGRAM.evaluate(False, client=client)
        self.assertEqual((result["required_pass"], result["observations"], result["injected_attempts"], result["outcome"]),
                         (70, 16, 172, "OFFLINE_COMPOSITE_INJECTED_PROVIDER_UNPROVEN"))
        self.assertEqual(len(client.received), 86)
        self.assertFalse(any("fixture@example.invalid" in text for text in client.received))
        self.assertEqual(sum("EMAIL_ADDRESS" in text for text in client.received), 3)

    def test_provider_miss_on_obfuscated_email_still_fails_and_stops(self):
        result = PROGRAM.evaluate(False, client=SimulatedGoogle(drop={"PORTFOLIO_OBFUSCATED_EMAIL"}))
        last = result["cases"][-1]
        self.assertEqual((last["case_id"], last["status"], result["required_fail"], result["outcome"]),
                         ("context-057", "FAIL", 1, "FAIL_CLOSED"))
        VALIDATOR.validate(self.write(result))

    def test_live_requires_both_acknowledgements_and_no_client(self):
        with self.assertRaises(adapter.GoogleSDPFailure):
            PROGRAM.evaluate(True)
        os.environ.update(PROGRAM.ACKS)
        try:
            with self.assertRaises(adapter.GoogleSDPFailure):
                PROGRAM.evaluate(True, client=SimulatedGoogle())
        finally:
            for key in PROGRAM.ACKS:
                os.environ.pop(key)

    def test_restore_maps_coordinates_and_rejects_token_overlap(self):
        det = PROGRAM.detector()
        text = "Email: fixture@example.invalid\nNational ID: 0000000000"
        spans = det.email_spans(text)
        masked = det.mask(text, spans)
        start = masked.index("0000000000")
        restored = PROGRAM.restore(spans, [(start, start + 10, "PORTFOLIO_NATIONAL_ID")], load_policy()["mapping"], det.TOKEN)
        self.assertEqual(restored, {(text.index("0000000000"), text.index("0000000000") + 10, "SAUDI_NATIONAL_ID")})
        token = masked.index("EMAIL_ADDRESS")
        self.assertEqual(PROGRAM.restore(spans, [(token, token + 5, "EMAIL_ADDRESS")], load_policy()["mapping"], det.TOKEN),
                         {(token, token + 5, "TOKEN_OVERLAP")})

    def write(self, value):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(value, handle); handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_validator_rejects_tampering_and_google_claims(self):
        good = PROGRAM.evaluate(False)
        mutations = [lambda v: v.update(google_qualification_claimed=True), lambda v: v.update(scope="context_pattern_v1_campaign"),
                     lambda v: v.update(policy_sha256="0" * 64), lambda v: v.update(deterministic_email_sha256="0" * 64),
                     lambda v: v.update(deterministic_email_cases=2), lambda v: v.update(required_pass=69),
                     lambda v: v.update(metadata_sdk_attempts=1), lambda v: v.update(extra=1),
                     lambda v: v["cases"][0].update(status="FAIL"), lambda v: v["cases"].pop(),
                     lambda v: v.update(mode="live_synthetic"), lambda v: v.update(sdk_attempts=1)]
        for mutate in mutations:
            value = json.loads(json.dumps(good)); mutate(value)
            with self.assertRaises(Exception):
                VALIDATOR.validate(self.write(value))

    def test_google_only_validator_unchanged_and_rejects_composite_scope(self):
        with self.assertRaises(Exception):
            GOOGLE_VALIDATOR.validate(self.write(PROGRAM.evaluate(False)))
        pins = {"scripts/validate-sdp-context-campaign-result.py": "eb83522412ca17796353ab9a2153ea04201af4a26ed36003942b84a1c2459255",
                "scripts/evaluate-sdp-context-policy.py": "4f4000a845c4bb69f28c489d872da65f1240f0b181e53181feebb9f47b36c5d9"}
        for path, digest in pins.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest, path)


class ImageEquivalentExecution(unittest.TestCase):
    """The exact rendered -c program runs with only the frozen SDP image files present."""

    def run_rendered(self, code):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "app"
            for relative in IMAGE_FILES:
                (app / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, app / relative)
            self.assertFalse((app / "runtime/phase3/deterministic_email.py").exists())
            code = code.replace('Path("/app") if "__file__" not in globals()', 'Path(' + repr(str(app)) + ') if "__file__" not in globals()', 1)
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            return subprocess.run([sys.executable, "-B", "-c", code], cwd=directory, capture_output=True, text=True, env=env, timeout=120)

    def test_rendered_program_matches_file_based_reference(self):
        code = PROGRAM.rendered_source(ROOT)
        self.assertEqual(code.count("\nEMBEDDED_DETERMINISTIC_EMAIL = None"), 0)
        self.assertEqual(code.count("\nEMBEDDED_DETERMINISTIC_EMAIL = '"), 1)
        completed = self.run_rendered(code)
        self.assertEqual(completed.returncode, 0, completed.stderr[-500:])
        self.assertEqual(json.loads(completed.stdout), PROGRAM.evaluate(False))

    def test_tampered_embedded_module_is_rejected_at_startup(self):
        code = PROGRAM.rendered_source(ROOT).replace("_TLD = r", "_TLD  = r", 1)
        completed = self.run_rendered(code)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(json.loads(completed.stdout)["diagnostic"], {"code": "CONFIGURATION_REJECTED", "stage": "startup"})


class DeploymentProfile(unittest.TestCase):
    def test_rendered_job_matches_validator_and_bounds(self):
        P = "project-b1e55144-cfd4-4fef-89a"
        digest = "us-east1-docker.pkg.dev/" + P + "/sdp-evaluation-images/google-sdp-context@sha256:667ceec4b8290df1341a91a7685ad140319fca6d23f92b9948dddf9fac64136b"
        rendered = subprocess.run(["bash", str(ROOT / "scripts/render-sdp-composite-email-campaign-job.sh"), P,
                                   "google-sdp-runtime@" + P + ".iam.gserviceaccount.com", digest], capture_output=True, text=True, check=True).stdout
        directory = next(line.split(": ", 1)[1].rsplit("/", 1)[0] for line in rendered.splitlines() if line.startswith("Controls: "))
        try:
            import yaml
            job = yaml.safe_load(Path(directory, "google-sdp-evaluation-job.yaml").read_text())
            container = job["spec"]["template"]["spec"]["containers"][0]
            self.assertEqual((job["spec"]["suspend"], job["spec"]["backoffLimit"], job["spec"]["activeDeadlineSeconds"]), (True, 0, 900))
            self.assertEqual(container["args"][1], PROGRAM.rendered_source(ROOT))
            self.assertEqual(job["metadata"]["annotations"]["portfolio.example/program-sha256"], hashlib.sha256(container["args"][1].encode()).hexdigest())
            self.assertEqual(container["image"], digest)  # unchanged SDP image subject
            bad = Path(directory, "google-sdp-evaluation-job.yaml")
            bad.write_text(bad.read_text().replace("'172'", "'173'"))
            self.assertNotEqual(subprocess.run([sys.executable, str(ROOT / "scripts/validate-sdp-composite-email-campaign-deployment.py"),
                                                str(Path(directory, "google-sdp-evaluation.yaml"))], capture_output=True).returncode, 0)
        finally:
            subprocess.run(["bash", str(ROOT / "scripts/render-sdp-composite-email-campaign-job.sh"), "--cleanup", directory], capture_output=True)


if __name__ == "__main__":
    unittest.main()
