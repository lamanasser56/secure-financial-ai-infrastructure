"""Prepared live path: local admission/HTTP objects only, zero provider calls."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class AdmissionTests(unittest.TestCase):
    def test_completed_finance_cannot_skip_facts_or_cross_tenant_total(self):
        app = load('run-synthetic-live-catalog')
        for user, total in (('alpha', 24000), ('beta', 9000)):
            entry = {'agent': 'financial', 'user': user}
            response = {'status': 'completed', 'facts': [
                {'tool_id': 'expense_summary', 'result': {'total_minor_units': total}},
                {'tool_id': 'expense_categories', 'result': {}}]}
            app.accept_catalog_result(entry, response)
            for value in (0, True, str(total), 9000 if user == 'alpha' else 24000):
                altered = copy.deepcopy(response)
                altered['facts'][0]['result']['total_minor_units'] = value
                with self.assertRaises(ValueError): app.accept_catalog_result(entry, altered)
            with self.assertRaises(ValueError): app.accept_catalog_result(entry, dict(response, facts=[]))

    def test_infrastructure_requires_each_governed_evidence_kind(self):
        app = load('run-synthetic-live-catalog')
        entry = {'agent': 'infrastructure', 'user': 'alpha'}
        facts = [{'tool_id': x, 'result': {}} for x in (
            'read_ci_summary', 'read_image_summary', 'read_runbook_section')]
        app.accept_catalog_result(entry, {'status': 'completed', 'facts': facts})
        for missing in range(3):
            with self.assertRaises(ValueError):
                app.accept_catalog_result(entry, {'status': 'completed', 'facts': facts[:missing] + facts[missing + 1:]})
        with self.assertRaises(ValueError):
            app.accept_catalog_result(entry, {'status': 'completed', 'facts': facts + facts[:1]})

    def test_current_catalog_never_grants_live_authority(self):
        app = load('run-synthetic-live-catalog')
        raw = (ROOT / 'evaluation/agent-composition/synthetic-demo.json').read_bytes()
        admission = {'schema_version': 1, 'scope': 'server_controlled_synthetic_two_agent_demo',
            'approved': True, 'source_commit': 'a' * 40, 'catalog_sha256': app.CATALOG_HASH,
            'processor_review': True, 'fixture_issuer_accepted': True,
            'program_sha256': 'b' * 64, 'gateway_configuration_sha256': 'c' * 64,
            'expires_at': time.time() + 30,
            'redaction_qualification': {'status': 'QUALIFIED_FOR_THIS_SYNTHETIC_CATALOG',
                'policy_sha256': 'c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db',
                'evidence_sha256': 'd' * 64}}
        # A constructed admission tests parsing only; no client is constructed.
        with mock.patch.dict(os.environ, {'PORTFOLIO_SYNTHETIC_LIVE_DEMO_ACK': app.ACK}, clear=True):
            app.admit(admission, raw)
            for field, value in (('approved', False), ('processor_review', False),
                                 ('fixture_issuer_accepted', False), ('expires_at', time.time() - 1),
                                 ('source_commit', 'branch'), ('catalog_sha256', '0' * 64)):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    app.admit(dict(admission, **{field: value}), raw)
            rejected = copy.deepcopy(admission)
            rejected['redaction_qualification']['status'] = 'CAMPAIGN_NOT_QUALIFIED'
            with self.assertRaises(ValueError): app.admit(rejected, raw)
            with self.assertRaises(ValueError): app.admit(admission, raw + b' ')
            with mock.patch.dict(os.environ, {'LITELLM_MASTER_KEY': 'never-an-app-key'}):
                with self.assertRaises(ValueError): app.admit(admission, raw)

    def test_durable_shared_reservations_reopen_and_exhaust(self):
        app = load('run-synthetic-live-catalog')
        with tempfile.TemporaryDirectory() as name:
            Path(name).chmod(0o700)
            journal = app.Reservations(Path(name)); journal.expires = time.time() + 30
            for _ in range(8): journal.reserve('model', 'local-fixture-alpha')
            with self.assertRaises(Exception): journal.reserve('model', 'local-fixture-alpha')
            for _ in range(8): journal.reserve('model', 'local-fixture-beta')
            for _ in range(12): journal.reserve('tool')
            with self.assertRaises(Exception): journal.reserve('tool')
            journal.reserve('redaction_input', amount=4096)
            journal.reserve('redaction_output', amount=4096)
            journal.close()
            reopened = app.Reservations(Path(name)); reopened.expires = time.time() + 30
            totals, subjects = reopened.totals()
            self.assertEqual((totals['model'], totals['tool'], totals['bytes']), (16, 12, 8192))
            self.assertEqual(set(subjects.values()), {8})
            reopened.expires = time.time() - 1
            with self.assertRaises(Exception): reopened.reserve('redaction_input')
            reopened.close()

    def test_neutral_transport_rejects_unknown_categories_and_consumes_failure(self):
        app = load('run-synthetic-live-catalog')
        with tempfile.TemporaryDirectory() as name:
            Path(name).chmod(0o700)
            journal = app.Reservations(Path(name)); journal.expires = time.time() + 30
            redactor = app.NeutralHTTPRedactor('a' * 64, journal)
            with mock.patch.object(app, '_post_json', return_value={'text': '123 SAR', 'categories': ['UNKNOWN']}):
                with self.assertRaises(Exception): redactor.redact('123 SAR')
            self.assertEqual(journal.totals()[0]['redaction_input'], 1)
            self.assertEqual(journal.totals()[0]['redaction_output'], 0)
            journal.close()

    def test_bridge_ledger_reserves_failed_attempts_and_blocks_replay(self):
        bridge = load('serve-synthetic-demo-redactor')
        with tempfile.TemporaryDirectory() as name:
            Path(name).chmod(0o700)
            ledger = bridge.Journal(Path(name), time.time() + 30)
            for _ in range(87): ledger.reserve()
            self.assertEqual(ledger.reserved(), 174)
            with self.assertRaises(Exception): ledger.reserve()
            with self.assertRaises(FileExistsError): bridge.Journal(Path(name), time.time() + 30)
            ledger.path.write_bytes(b'2\n2')
            with self.assertRaises(Exception): ledger.reserved()

    def test_actual_local_bridge_http_denial_before_simulated_boundary(self):
        bridge = load('serve-synthetic-demo-redactor')
        from runtime.phase3.trusted_runtime import RedactionResult
        from runtime.phase3.google_sdp_adapter import GoogleSDPFailure
        with tempfile.TemporaryDirectory() as name:
            Path(name).chmod(0o700)
            with bridge.Server(('127.0.0.1', 0), bridge.Handler) as server:
                server.key = 'a' * 64
                server.failed, server.diagnostic = False, None
                server.journal = bridge.Journal(Path(name), time.time() + 30)
                server.redactor = mock.Mock()
                server.redactor.redact.return_value = RedactionResult('123 SAR', ())
                thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
                url = 'http://127.0.0.1:' + str(server.server_port) + '/redact'
                def call(key, body):
                    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
                    try:
                        with urllib.request.urlopen(req, timeout=2) as response: return response.status, json.load(response)
                    except urllib.error.HTTPError as error: return error.code, json.load(error)
                self.assertEqual(call('wrong', b'{"text":"123 SAR"}')[0], 403)
                server.redactor.redact.assert_not_called(); self.assertEqual(server.journal.reserved(), 0)
                self.assertEqual(call(server.key, b'{"text":"123 SAR"}')[0], 200)
                self.assertEqual(server.journal.reserved(), 2)
                server.redactor.redact.side_effect = GoogleSDPFailure('RPC_TIMEOUT', 'deidentify')
                status, value = call(server.key, b'{"text":"123 SAR"}')
                self.assertEqual(status, 503); self.assertTrue(server.failed)
                self.assertEqual(server.journal.reserved(), 4)
                self.assertNotIn('text', value); self.assertNotIn('message', value)
                server.shutdown(); thread.join(timeout=2)

    def test_exact_manifest_and_mutations(self):
        render = load('render-synthetic-demo-bundle')
        prefix = 'us-east1-docker.pkg.dev/project-fixture/sdp-evaluation-images/agent-demo-'
        images = [prefix + name + '@sha256:' + 'a' * 64 for name in ('gateway', 'application', 'database')]
        subject = render.bundle('project-fixture', *images)
        jobs = [x for x in subject['items'] if x['kind'] == 'Job']
        self.assertEqual(len(jobs), 6)
        for job in jobs:
            self.assertTrue(job['spec']['suspend']); self.assertEqual(job['spec']['backoffLimit'], 0)
            self.assertEqual(job['spec']['activeDeadlineSeconds'], 120 if job['metadata']['name'].endswith('preflight') else 900)
        app = next(x for x in jobs if x['metadata']['name'] == 'catalog')
        self.assertFalse(app['spec']['template']['spec']['automountServiceAccountToken'])
        for mutation in ('deadline', 'args', 'retry', 'security', 'public', 'secret', 'selector'):
            altered = copy.deepcopy(subject)
            row = next(x for x in altered['items'] if x['kind'] == 'Job')
            pod = row['spec']['template']['spec']
            if mutation == 'deadline': row['spec']['activeDeadlineSeconds'] += 1
            elif mutation == 'args': pod['containers'][0]['args'].append('--live')
            elif mutation == 'retry': row['spec']['backoffLimit'] = 1
            elif mutation == 'security': pod['hostNetwork'] = True
            elif mutation == 'public': altered['items'].append({'kind': 'Ingress'})
            elif mutation == 'secret': pod['volumes'][0]['secret']['secretName'] = 'unreviewed'
            else: row['spec']['template']['metadata']['labels']['app'] = 'gateway'
            with self.assertRaises(ValueError): render.validate_document(altered, subject)
        with self.assertRaises(ValueError): render.bundle('project-fixture', images[0].split('@')[0], *images[1:])


if __name__ == '__main__':
    unittest.main()
