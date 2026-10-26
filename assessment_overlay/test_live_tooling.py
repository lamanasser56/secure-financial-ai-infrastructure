"""Offline checks for the fixed provider and main-render gateway transform."""

import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from types import SimpleNamespace

import yaml

from patch_gateway_stub import STUB_URL, patch
from provider_stub import make_server
from render_live_bundle import make_bundle
from stage_live_bundle import split


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = Path(__file__).resolve().parent
PROJECT = 'sfai-assess-test123'
SOURCE = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
IMAGES = {name: image + '@sha256:' + hashlib.sha256(name.encode()).hexdigest() for name, image in (
    ('gateway', 'agent-platform-gateway'), ('database', 'agent-platform-database'),
    ('redactor', 'agent-platform-redactor'), ('app', 'agent-platform-app'),
    ('ops-agent', 'agent-platform-ops'), ('agent-financial', 'agent-financial'),
    ('platform-guide', 'platform-guide'))}
IMAGE_LOCK = {'schema_version': 2, 'source_commit': SOURCE,
              'runtime_contract': 'trusted-boundaries-v2',
              'registry': 'us-east1-docker.pkg.dev/sfai-source-test123/sdp-evaluation-images/',
              'images': IMAGES}
APP = IMAGE_LOCK['registry'] + IMAGES['app']


def lock_file(directory):
    path = Path(directory) / 'current-images.json'
    path.write_text(json.dumps(IMAGE_LOCK))
    return path


class LiveToolingTest(unittest.TestCase):
    def test_historical_bundle_refuses_current_image_owned_redactor(self):
        with self.assertRaisesRegex(ValueError, 'current qualified image lock'):
            make_bundle('assess-0123456789abcdef', project=PROJECT,
                        images_lock=OVERLAY / 'platform-images.lock.json', passphrase='synthetic-test-only',
                        hasher=lambda passwords: {name: '$argon2id$synthetic-test-only'
                                                  for name in passwords})

    def test_full_current_bundle_stages_durable_limits_and_private_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            docs, receipt = make_bundle('assess-0123456789abcdef', project=PROJECT,
                images_lock=lock_file(temporary), passphrase='synthetic-test-only',
                runtime_registry='us-east1-docker.pkg.dev/' + PROJECT + '/sdp-evaluation-images/',
                hasher=lambda passwords: {name: '$argon2id$synthetic-test-only'
                                          for name in passwords})
        self.assertFalse(receipt['external_llm_route'])
        self.assertEqual(receipt['platform_commit'], SOURCE)
        self.assertEqual(receipt['image_digests'], IMAGES)
        self.assertEqual(receipt['runtime_registry'],
                         'us-east1-docker.pkg.dev/' + PROJECT + '/sdp-evaluation-images/')
        staged = split(docs)
        self.assertEqual(sum(map(len, staged)), len(docs))
        self.assertTrue(any(d['kind'] == 'Job' and d['metadata']['name'] == 'assessment-sdp-seed'
                            for d in docs))
        self.assertFalse(any('vertex_ai/' in json.dumps(d) for d in docs))
        service_accounts = {(d['metadata']['namespace'], d['metadata']['name']): d
                            for d in docs if d['kind'] == 'ServiceAccount'}
        self.assertNotIn('iam.gke.io/gcp-service-account',
                         service_accounts[('platform', 'gateway')]['metadata'].get('annotations', {}))
        self.assertEqual(service_accounts[('platform', 'redactor')]['metadata']['annotations'],
                         {'iam.gke.io/gcp-service-account':
                          f'google-sdp-runtime@{PROJECT}.iam.gserviceaccount.com'})
        metadata_policy = next(d for d in docs if d['kind'] == 'NetworkPolicy'
                               and d['metadata']['name'] == 'workload-identity-metadata')
        self.assertEqual(metadata_policy['spec']['podSelector']['matchExpressions'][0]['values'],
                         ['redactor'])

    def test_provider_is_fixed_and_counts_raw_canary_without_echoing_it(self):
        server = make_server('127.0.0.1', 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
            connection.request('POST', '/v1/chat/completions',
                               json.dumps({'messages': [{'role': 'user',
                                                         'content': 'Call PHONE_NUMBER.'}]}),
                               {'Content-Type': 'application/json'})
            response = connection.getresponse()
            body = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(body['model'], 'assessment-stub')
            self.assertEqual(body['choices'][0]['message']['content'],
                             '{"action":"answer","text":"Synthetic response."}')
            connection.request('GET', '/stats')
            stats = json.loads(connection.getresponse().read())
            self.assertEqual(stats, {'requests': 1, 'raw_canary_seen': False})
            connection.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_main_render_routes_only_to_private_stub_and_keeps_platform_bytes(self):
        spec = importlib.util.spec_from_file_location('assessment_main_render',
                    ROOT / 'platform/clouds/gke/render.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            args = SimpleNamespace(project_id=PROJECT,
                images_lock=str(lock_file(temporary)),
                control_plane_cidr='172.16.0.16/28',
                gateway_gsa=f'agent-platform-gateway@{PROJECT}.iam.gserviceaccount.com',
                redactor_gsa=f'google-sdp-runtime@{PROJECT}.iam.gserviceaccount.com',
                kubectl='kubectl')
            rendered, summary = module.render(args)
        self.assertEqual(summary['kinds']['ValidatingAdmissionPolicy'], 1)
        self.assertEqual(summary['kinds']['ValidatingAdmissionPolicyBinding'], 1)
        original = [doc for doc in yaml.safe_load_all(rendered) if doc]
        amended, receipt = patch(original, APP)
        find = lambda kind, ns, name: [d for d in amended if d['kind'] == kind
            and d['metadata'].get('namespace', '') == ns
            and d['metadata']['name'].startswith(name)]
        self.assertEqual(len(find('FQDNNetworkPolicy', 'platform', 'gateway-provider')), 0)
        self.assertEqual(len(find('FQDNNetworkPolicy', 'platform', 'redactor-provider')), 1)
        self.assertEqual(len(find('NetworkPolicy', 'platform', 'gateway-to-private-stub')), 1)
        self.assertEqual(len(find('NetworkPolicy', 'assess-probes', 'default-deny')), 1)
        self.assertEqual(find('Deployment', 'assess-probes', 'provider-stub')[0]
                         ['spec']['template']['spec']['containers'][0]['image'], APP)
        route = yaml.safe_load(find('ConfigMap', 'platform', 'gateway-config-')[0]
                               ['data']['litellm.yaml'])
        params = route['model_list'][0]['litellm_params']
        self.assertEqual(params['api_base'], STUB_URL)
        self.assertEqual(params['model'], 'openai/assessment-stub')
        self.assertEqual(params['max_retries'], 0)
        self.assertFalse(any('vertex_ai/' in json.dumps(doc) for doc in amended))
        self.assertEqual(receipt['stub_source_sha256'],
                         hashlib.sha256((OVERLAY / 'provider_stub.py').read_bytes()).hexdigest())
        self.assertEqual(find('ConfigMap', 'platform', 'platform-programs-'), [])
        self.assertFalse(any(d['kind'] == 'ConfigMap' and d['metadata'].get('namespace') == 'platform'
                             and d['metadata']['name'].startswith('platform-programs-') for d in original))


if __name__ == '__main__':
    unittest.main()
