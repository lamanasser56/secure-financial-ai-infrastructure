"""Offline security regressions for the proposed native execution boundary."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[2]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROBE = load("sdp_network_probe", "probe-google-sdp-egress.py")
VERIFY = load("sdp_network_verify", "verify-google-sdp-egress-evidence.py")
CONTRACT = load("sdp_execution_contract", "validate-google-sdp-execution.py")
TEST_PROJECT = "synthetic-eval-123"
ENV = {"PORTFOLIO_GOOGLE_SDP_NETWORK_PREFLIGHT_ACK": PROBE.ACK, "PORTFOLIO_GOOGLE_SDP_EXPECTED_GSA": f"google-sdp-runtime@{TEST_PROJECT}.iam.gserviceaccount.com"}
POD = "google-sdp-egress-preflight-abcde"


def observations():
    result = PROBE.observe(ENV, resolver=lambda host: ["8.8.4.4"] if host == PROBE.ENDPOINT else ["1.1.1.1"], tls_connect=lambda ip: None, denial=lambda ip, port: True, identity=lambda gsa: None)
    result.update(status="OBSERVATIONS_PASSED_AWAITING_DATAPATH_EVIDENCE", provider_operations=0, limitations=PROBE.LIMITATIONS, started_at="2026-10-03T00:00:00+00:00", finished_at="2026-10-03T00:00:40+00:00")
    return result


def log(ip, port, disposition):
    return {
        "resource": {"type": "k8s_node", "labels": {"cluster_name": "google-sdp-evaluation", "location": "us-east1-b", "project_id": "synthetic-eval-123"}},
        "logName": "projects/synthetic-eval-123/logs/policy-action",
        "jsonPayload": {"src": {"pod_name": POD, "namespace": "google-sdp-evaluation"}, "timestamp": "2026-10-03T00:00:10Z", "connection": {"dest_ip": ip, "dest_port": port, "protocol": "tcp", "direction": "egress"}, "disposition": disposition, "policies": [{"name": "google-sdp-evaluation-regional-egress", "namespace": "google-sdp-evaluation"}]},
    }


class NativeExecutionTests(unittest.TestCase):
    def test_current_proposed_contract_passes(self):
        CONTRACT.validate()

    def test_owner_profile_cannot_promote_itself_or_expand_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "evaluation", root / "evaluation")
            shutil.copytree(ROOT / "infra", root / "infra", ignore=shutil.ignore_patterns(".terraform"))
            path = root / "evaluation/google-sdp/execution-profile.json"
            initial = json.loads(path.read_text())
            for field, bad in (("status", "approved"), ("independent_review", True), ("separation_of_duties_proven", True), ("maximum_sdk_operations", 19), ("maximum_live_jobs", 2), ("application_retries", 1), ("real_data_authorized", True), ("production_authorized", True), ("presidio_authoritative", False), ("retain_evaluation_cluster", True), ("requires_explicit_complete_bundle_approval", False)):
                with self.subTest(field=field):
                    data = initial | {field: bad}
                    path.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):
                        CONTRACT.validate(root)

    def test_unsafe_cluster_changes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "evaluation", root / "evaluation")
            shutil.copytree(ROOT / "infra", root / "infra", ignore=shutil.ignore_patterns(".terraform"))
            path = root / "infra/gcp/google-sdp-evaluation-cluster/cluster.tf"
            original = path.read_text()
            for before, after in (
                ('"ADVANCED_DATAPATH"', '"LEGACY_DATAPATH"'), ('enable_fqdn_network_policy = true', 'enable_fqdn_network_policy = false'),
                ('node_count = 1', 'node_count = 3'), ('"us-east1-b"', '"us-west1-b"'),
                ('roles/container.defaultNodeServiceAccount', 'roles/editor'), ('enable_private_nodes    = true', 'enable_private_nodes    = false'),
                ('"KUBE_DNS"', '"CUSTOM_DNS"'), ('max_surge       = 0', 'max_surge       = 1'),
                ('service_account = google_service_account.node.email', 'service_account = "default"'),
            ):
                with self.subTest(before=before):
                    self.assertIn(before, original)
                    path.write_text(original.replace(before, after))
                    with self.assertRaises(ValueError):
                        CONTRACT.validate(root)

    def test_preflight_has_no_default_network_execution(self):
        with patch.object(PROBE, "observe", side_effect=AssertionError("network forbidden")), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(PROBE.main([], {}), 2)
        self.assertEqual(json.loads(output.getvalue())["provider_operations"], 0)

    def test_preflight_ack_identity_and_proxy_guards(self):
        bad_values = [{}, ENV | {"PORTFOLIO_GOOGLE_SDP_NETWORK_PREFLIGHT_ACK": "yes"}, ENV | {"PORTFOLIO_GOOGLE_SDP_EXPECTED_GSA": "default@example.com"}, ENV | {"grpc_proxy": "http://unapproved.invalid"}]
        for values in bad_values:
            with self.subTest(values=values), self.assertRaises(ValueError):
                PROBE.observe(values, resolver=lambda host: self.fail("network before controls"))

    def test_shared_ip_targets_cannot_claim_unrelated_isolation(self):
        with self.assertRaises(ValueError):
            PROBE.observe(ENV, resolver=lambda host: ["8.8.4.4"], identity=lambda gsa: self.fail("identity before overlap check"))

    def test_connectivity_probes_are_bounded_and_send_no_dlp(self):
        calls = []
        result = PROBE.observe(ENV, resolver=lambda host: ["8.8.4.4"] if host == PROBE.ENDPOINT else ["1.1.1.1"], tls_connect=lambda ip: calls.append((ip, 443, "tls")), identity=lambda gsa: calls.append("identity"), denial=lambda ip, port: calls.append((ip, port, "negative")) or True)
        self.assertEqual(len(result["probes"]), 4)
        self.assertEqual(len(calls), 6)
        self.assertEqual({probe["test"] for probe in result["probes"]}, {"unrelated_resolved_https", "unrelated_direct_ip", "alternate_https_route", "alternate_dns_route"})

    def test_any_unapproved_connection_fails_without_fallback(self):
        calls = []
        with self.assertRaises(ValueError):
            PROBE.observe(ENV, resolver=lambda host: ["8.8.4.4"] if host == PROBE.ENDPOINT else ["1.1.1.1"], tls_connect=lambda ip: None, identity=lambda gsa: None, denial=lambda ip, port: calls.append((ip, port)) or False)
        self.assertEqual(len(calls), 1)

    def test_probe_failure_is_sanitized(self):
        with patch.object(PROBE, "observe", side_effect=RuntimeError("sensitive-token-and-provider-response")), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(PROBE.main(["--network-preflight"], ENV), 2)
        self.assertNotIn("sensitive-token", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["status"], "FAIL")

    def test_timeouts_without_datapath_verdicts_never_pass(self):
        with self.assertRaises(ValueError):
            VERIFY.verify(observations(), [], POD)

    def test_matching_allow_and_all_deny_verdicts_verify_ip_port_only(self):
        observed = observations()
        logs = [log(observed["positive_ip"], 443, "allow")] + [log(p["destination_ip"], p["port"], "deny") for p in observed["probes"]]
        result = VERIFY.verify(observed, logs, POD)
        self.assertEqual(result["status"], "VERIFIED_IP_PORT_BOUNDARY")
        self.assertIn("shared_ip_not_hostname_isolation", result["limitations"])

    def test_wrong_cluster_pod_time_direction_or_incomplete_logs_rejected(self):
        observed = observations()
        original = [log(observed["positive_ip"], 443, "allow")] + [log(p["destination_ip"], p["port"], "deny") for p in observed["probes"]]
        for mutation in ("cluster", "pod", "time", "direction", "missing_deny", "wrong_policy", "wrong_log"):
            with self.subTest(mutation=mutation):
                logs = copy.deepcopy(original)
                if mutation == "missing_deny":
                    logs = [entry for entry in logs if entry["jsonPayload"]["connection"]["dest_port"] != 53]
                for entry in logs:
                    if mutation == "cluster":
                        entry["resource"]["labels"]["cluster_name"] = "other-cluster"
                    elif mutation == "pod":
                        entry["jsonPayload"]["src"]["pod_name"] = "other-pod"
                    elif mutation == "time":
                        entry["jsonPayload"]["timestamp"] = "2026-10-03T01:00:00Z"
                    elif mutation == "direction":
                        entry["jsonPayload"]["connection"]["direction"] = "ingress"
                    elif mutation == "wrong_policy":
                        entry["jsonPayload"]["policies"][0]["name"] = "broad-https"
                    elif mutation == "wrong_log":
                        entry["logName"] = "untrusted-local-log"
                with self.assertRaises(ValueError):
                    VERIFY.verify(observed, logs, POD)

    def test_preflight_render_uses_same_digest_and_readonly_reviewed_code(self):
        project = "synthetic-eval-123"
        digest = f"me-central2-docker.pkg.dev/{project}/synthetic-repo/evaluation@sha256:" + "a" * 64
        result = subprocess.run(["bash", str(ROOT / "scripts/render-google-sdp-evaluation-job.sh"), project, ENV["PORTFOLIO_GOOGLE_SDP_EXPECTED_GSA"], digest], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        directory = Path(next(line.split(": ", 1)[1] for line in result.stdout.splitlines() if line.startswith("Rendered manifest:"))).parent
        try:
            config, job = list(yaml.safe_load_all((directory / "google-sdp-egress-preflight.yaml").read_text()))
            container = job["spec"]["template"]["spec"]["containers"][0]
            self.assertEqual(container["image"], digest)
            self.assertEqual(config["data"]["probe.py"], (ROOT / "scripts/probe-google-sdp-egress.py").read_text())
            self.assertTrue(container["volumeMounts"][0]["readOnly"])
            self.assertEqual(job["spec"]["activeDeadlineSeconds"], 180)
            self.assertEqual(job["spec"]["backoffLimit"], 0)
            container["securityContext"]["allowPrivilegeEscalation"] = True
            (directory / "google-sdp-egress-preflight.yaml").write_text(yaml.safe_dump_all([config, job]))
            rejected = subprocess.run(["bash", str(ROOT / "scripts/validate-google-sdp-deployment.sh"), str(directory / "google-sdp-evaluation.yaml")], capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
        finally:
            subprocess.run(["bash", str(ROOT / "scripts/render-google-sdp-evaluation-job.sh"), "--cleanup", str(directory)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
