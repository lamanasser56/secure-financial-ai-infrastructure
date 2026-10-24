"""Local protocol tests for the assessment overlay; no cloud or real SDP calls."""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('ASSESSMENT_RUN_ID', 'assess-0000000000000001')

from phone_guard import mask_phones
from redactor_server import CompletionBudget, load_platform
from sdp_guard import CompletedLedger, Exhausted, Ledger, LimitedClient
from seed_sdp import seed
from patch_ops_stub import patch as patch_ops_stub, assert_order
from patch_redactor_bundle import patch as patch_redactor_bundle


MAIN_SHA = '41ffbf260a446b5db2292356a8ea23219e58a524'
ROOT = Path(__file__).resolve().parents[1]


def main_file(path):
    return subprocess.run(['git', 'show', f'{MAIN_SHA}:{path}'], cwd=ROOT,
                          capture_output=True, check=True).stdout


def main_redactor(directory):
    programs = Path(directory)
    (programs / 'redactor_server.py').write_bytes(main_file(
        'platform/core/src/agent_platform/programs/redactor_server.py'))
    (programs / 'phone_guard.py').write_bytes(main_file(
        'platform/core/src/agent_platform/programs/phone_guard.py'))
    return load_platform(programs / 'redactor_server.py')


class _Result:
    def __init__(self, text):
        self.text, self.categories = text, ()


class _FakeRedactor:
    def __init__(self):
        self.inputs = []

    def redact(self, text):
        self.inputs.append(text)
        return _Result(text)


class _Budget:
    def __init__(self, redactor):
        self.redactor = redactor

    def current(self):
        return self.redactor


class _Client:
    api_endpoint = 'synthetic-only'
    transport = None

    def __init__(self):
        self.calls = 0

    def inspect_content(self, *, request, retry, timeout):
        self.calls += 1
        return {}


class FollowupTests(unittest.TestCase):
    def test_inline_phone_forms_and_neutral_text(self):
        cases = (
            'Call +1 202-555-0101 tomorrow.',
            'Call (202) 555-0101 tomorrow.',
            'Call 2025550101 tomorrow.',
            'Call +966512345678 tomorrow.',
            'Call +966 55 123 4567 tomorrow.',
            'Call +966-55-123-4567 tomorrow.',
            'Call 0551234567 tomorrow.',
            'Call 055-123-4567 tomorrow.',
            'اتصل على ٠٥٥ ١٢٣ ٤٥٦٧ غدا.',
            'اتصل على +٩٦٦-٥٥-١٢٣-٤٥٦٧ غدا.',
            '{"note": "Call +1 202-555-0101 tomorrow."}',
            'First line\nاتصل على ٠٥٥ ١٢٣ ٤٥٦٧ غدا.',
        )
        for value in cases:
            with self.subTest(form=value[:8]):
                masked, found = mask_phones(value)
                self.assertTrue(found)
                self.assertIn('PHONE_NUMBER', masked)
                self.assertNotEqual(masked, value)
        for value in ('Invoice 2026-10-24 total SAR 1234.50', 'User id 1234567890',
                      'Call 05512345678 tomorrow', 'Call +9665123456789 tomorrow'):
            self.assertEqual(mask_phones(value), (value, False))

    def test_21st_response_refused_and_restart_keeps_both_ledgers(self):
        with tempfile.TemporaryDirectory() as temporary:
            seed(temporary)
            with self.assertRaises(RuntimeError):
                seed(temporary)
            root = Path(temporary)
            platform = main_redactor(root)
            redactor = _FakeRedactor()

            def serve():
                keys = {'app': 'a' * 64, 'ops': 'b' * 64}
                server = platform.Server(('127.0.0.1', 0), keys,
                    CompletionBudget(_Budget(redactor), CompletedLedger(root / 'sdp-completions.json')),
                    capacity=platform.Capacity(keys, per_client_window=30, global_window=30))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                return server, thread

            def call(server, text):
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                body = json.dumps({'text': text})
                client.request('POST', '/redact', body, {
                    'Content-Type': 'application/json', 'Authorization': 'Bearer ' + 'a' * 64,
                })
                result = client.getresponse()
                status, value = result.status, json.loads(result.read())
                client.close()
                return status, value

            server, thread = serve()
            try:
                status, value = call(server, 'Call +1 202-555-0101 tomorrow.')
                self.assertEqual(status, 200)
                self.assertEqual(value['text'], 'Call PHONE_NUMBER tomorrow.')
                self.assertEqual(value['categories'], ['PHONE_NUMBER'])
                self.assertNotIn('+1 202-555-0101', redactor.inputs[0])
                for _ in range(19):
                    self.assertEqual(call(server, 'synthetic no phone')[0], 200)
                self.assertEqual(call(server, 'synthetic no phone')[0], 503)
            finally:
                server.shutdown();server.server_close();thread.join(timeout=3)
            server, thread = serve()  # stand-in for a restarted pod on the same PVC
            try:
                self.assertEqual(call(server, 'synthetic no phone')[0], 503)
            finally:
                server.shutdown();server.server_close();thread.join(timeout=3)
            self.assertEqual(len(redactor.inputs), 20)
            self.assertEqual(json.loads((root / 'sdp-completions.json').read_text())['completed'], 20)
            self.assertEqual(json.loads((root / 'sdp-attempts.json').read_text())['used'], 0)

            client = _Client()
            limited = LimitedClient(client, root / 'sdp-attempts.json')
            for _ in range(60):
                limited.inspect_content(request={}, retry=None, timeout=1)
            with self.assertRaises(Exhausted):
                LimitedClient(client, root / 'sdp-attempts.json').inspect_content(
                    request={}, retry=None, timeout=1)
            self.assertEqual(client.calls, 60)
            self.assertEqual(json.loads((root / 'sdp-attempts.json').read_text())['used'], 60)

    def test_crash_reservation_survives_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            seed(temporary)
            path = Path(temporary) / 'sdp-completions.json'
            ledger = CompletedLedger(path)
            tokens = [ledger.reserve() for _ in range(20)]
            with self.assertRaises(Exhausted):
                CompletedLedger(path).reserve()
            ledger.abort(tokens[0])
            new_token = CompletedLedger(path).reserve()
            self.assertEqual(ledger.complete(new_token), 1)
            self.assertEqual(json.loads(path.read_text())['completed'], 1)
            path.write_text('{corrupt')
            with self.assertRaises((ValueError, Exhausted)):
                CompletedLedger(path).reserve()

    def test_ops_explanation_is_stub_only_and_bundle_removes_keys(self):
        from ops_server_assessment import assessment_build, stub_explanation
        with tempfile.TemporaryDirectory() as temporary:
            config = {'api_key': 'synthetic', 'approver_public_key': 'synthetic',
                      'gateway_key': '', 'redactor_key': '', 'executor_key': 'synthetic'}
            Path(temporary, 'ops.json').write_text(json.dumps(config))
            agent = SimpleNamespace(explainer=None)
            with patch('ops_server_assessment._normal_build', return_value=(agent, 'synthetic')) as normal:
                built, _ = assessment_build(Path(temporary), Path(temporary), Path(temporary))
            self.assertIs(built, agent)
            self.assertEqual(normal.call_count, 1)
            self.assertEqual(built.explainer({})['source'], 'assessment_stub')
            self.assertEqual(stub_explanation({'raw': 'phone'})['untrusted_text'],
                             'Synthetic assessment explanation.')
            config['gateway_key'] = 'would-connect'
            Path(temporary, 'ops.json').write_text(json.dumps(config))
            with self.assertRaises(SystemExit):
                assessment_build(Path(temporary), Path(temporary), Path(temporary))

        original = {'api_key': 'synthetic', 'approver_public_key': 'synthetic',
                    'gateway_key': 'synthetic-gateway', 'redactor_key': 'synthetic-redactor',
                    'executor_key': 'synthetic'}
        deployment = {'kind': 'Deployment', 'metadata': {'namespace': 'ops', 'name': 'ops-agent'},
                      'spec': {'template': {'spec': {'containers': [{
                          'name': 'ops-agent',
                          'command': ['/usr/local/bin/python3.12', '-m', 'agent_platform.ops.server']}],
                          'volumes': []}}}}
        secret = {'kind': 'Secret', 'metadata': {'namespace': 'ops', 'name': 'ops-agent'},
                  'stringData': {'ops.json': json.dumps(original)}}
        registry = {'kind': 'ConfigMap', 'metadata': {'namespace': 'ops', 'name': 'ops-agent-registry'}}
        binding = {'kind': 'ValidatingAdmissionPolicyBinding',
                   'metadata': {'name': 'ops-agent-bounded-remediation'}}
        docs = patch_ops_stub([registry, binding, secret, deployment],
                              Path(__file__).with_name('ops_server_assessment.py'))
        assert_order(docs)
        changed = json.loads(secret['stringData']['ops.json'])
        self.assertEqual((changed['gateway_key'], changed['redactor_key']), ('', ''))
        self.assertEqual(deployment['spec']['template']['spec']['containers'][0]['command'][-1],
                         '/assessment/ops_server_assessment.py')
        with self.assertRaises(ValueError):
            assert_order([binding, registry, *docs[2:]])

    def test_assessment_uses_main_f7_capacity_and_phone_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            seed(temporary)
            platform = main_redactor(temporary)
            keys = {'app': 'a' * 64, 'ops': 'b' * 64}
            entered, release = threading.Event(), threading.Event()

            class BlockingRedactor(_FakeRedactor):
                def redact(self, text):
                    if not entered.is_set():
                        entered.set()
                        if not release.wait(3):
                            raise RuntimeError('synthetic block timeout')
                    return super().redact(text)

            redactor = BlockingRedactor()
            server = platform.Server(('127.0.0.1', 0), keys,
                CompletionBudget(_Budget(redactor),
                                 CompletedLedger(Path(temporary) / 'sdp-completions.json')),
                capacity=platform.Capacity(keys, per_client_window=2, global_window=3))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def call(client_name, text='synthetic text'):
                conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    conn.request('POST', '/redact', json.dumps({'text': text}), {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + keys[client_name]})
                    response = conn.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    conn.close()

            first = []
            try:
                caller = threading.Thread(target=lambda: first.append(call('app',
                    'Call +1 202-555-0101 tomorrow.')), daemon=True)
                caller.start()
                self.assertTrue(entered.wait(3))
                self.assertEqual(call('app')[0], 429)  # per-client in flight
                self.assertEqual(call('ops')[0], 429)  # global in flight
                release.set()
                caller.join(timeout=5)
                self.assertEqual(first[0][0], 200)
                self.assertEqual(first[0][1]['categories'], ['PHONE_NUMBER'])
                self.assertNotIn('+1 202-555-0101', redactor.inputs[0])
                self.assertEqual(call('app')[0], 200)
                self.assertEqual(call('app')[0], 429)  # per-client window
                self.assertEqual(call('ops')[0], 200)
                self.assertEqual(call('ops')[0], 429)  # global window
                self.assertIs(server.capacity.__class__, platform.Capacity)
            finally:
                release.set()
                server.shutdown();server.server_close();thread.join(timeout=3)

    def test_main_f15_client_does_not_follow_redirect(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'main_redaction.py'
            source.write_bytes(main_file('platform/core/src/agent_platform/redaction.py'))
            spec = importlib.util.spec_from_file_location('_qualified_main_redaction', source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            first, redirected = [], []

            class Redirect(BaseHTTPRequestHandler):
                def log_message(self, *_):
                    pass

                def do_POST(self):
                    first.append(self.path)
                    self.send_response(302)
                    self.send_header('Location', f'http://127.0.0.1:{self.server.server_port}/sink')
                    self.end_headers()

                def do_GET(self):
                    redirected.append(self.path)
                    self.send_response(200)
                    self.end_headers()

            server = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                budget = SimpleNamespace(reserve=lambda _: None, accept_output=lambda _: None)
                client = module.RedactorClient(f'http://127.0.0.1:{server.server_port}',
                                               'a' * 64, budget=budget)
                with self.assertRaises(module.ControlFailure):
                    client.redact('synthetic text')
                self.assertEqual(first, ['/redact'])
                self.assertEqual(redirected, [])
            finally:
                server.shutdown();server.server_close();thread.join(timeout=3)

    def test_source_render_wires_dual_ledger_without_policy_weakening(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        rendered = subprocess.run(['kubectl', 'kustomize', '--load-restrictor=LoadRestrictionsNone',
                                   'platform/core/kubernetes'], cwd=root, capture_output=True, text=True,
                                  check=True, timeout=30)
        docs = [d for d in yaml.safe_load_all(rendered.stdout) if d]
        programs = next(d for d in docs if d['kind'] == 'ConfigMap' and
                        d['metadata']['namespace'] == 'platform' and
                        d['metadata']['name'].startswith('platform-programs-'))
        # This evidence branch predates F7; qualify the transform against the
        # exact current-main inputs rather than its historical local checkout.
        real_redactor = main_file('platform/core/src/agent_platform/programs/redactor_server.py').decode()
        real_phone = main_file('platform/core/src/agent_platform/programs/phone_guard.py').decode()
        programs['data']['redactor_server.py'] = real_redactor
        programs['data']['phone_guard.py'] = real_phone
        amended, preseed, redactor = patch_redactor_bundle(
            docs, Path(__file__).parent, 'assess-0000000000000001')
        self.assertEqual(programs['data']['redactor_server.py'], real_redactor)
        self.assertEqual(programs['data']['phone_guard.py'], real_phone)
        self.assertEqual(redactor['spec']['template']['spec']['containers'][0]['command'][-1],
                         '/assessment/redactor_server.py')
        self.assertLess(amended.index(preseed[2]), amended.index(redactor))
        synthetic_ops = {'kind': 'Secret', 'metadata': {'namespace': 'ops', 'name': 'ops-agent'},
                         'stringData': {'ops.json': json.dumps({
                             'api_key': 'synthetic', 'approver_public_key': 'synthetic',
                             'gateway_key': 'synthetic-gateway', 'redactor_key': 'synthetic-redactor',
                             'executor_key': 'synthetic'})}}
        amended = patch_ops_stub([*amended, synthetic_ops],
                                 Path(__file__).with_name('ops_server_assessment.py'))
        assert_order(amended)
        self.assertEqual([d['kind'] for d in preseed], ['ConfigMap', 'PersistentVolumeClaim', 'Job'])
        self.assertEqual(preseed[2]['spec']['template']['spec']['containers'][0]['command'][-1],
                         '/assessment-state')
        self.assertTrue(any(v['name'] == 'assessment-state' for v in
                            redactor['spec']['template']['spec']['volumes']))
        self.assertEqual(next(d for d in amended if d['kind'] == 'ResourceQuota' and
                              d['metadata']['name'] == 'bounds' and d['metadata']['namespace'] == 'platform')
                         ['spec']['hard']['requests.storage'], '11Gi')
        policy = root / 'evaluation/google-sdp-context/policy.json'
        import hashlib
        self.assertEqual(hashlib.sha256(policy.read_bytes()).hexdigest(),
                         'c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db')


if __name__ == '__main__':
    unittest.main()
