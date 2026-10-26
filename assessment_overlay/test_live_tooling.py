"""Offline checks for the fixed provider and main-render gateway transform."""

import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
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
IMAGE_LOCK = json.loads((OVERLAY / 'platform-images.lock.json').read_text())
APP = IMAGE_LOCK['registry'] + IMAGE_LOCK['images']['app']


class LiveToolingTest(unittest.TestCase):
    def test_historical_bundle_refuses_current_image_owned_redactor(self):
        with self.assertRaisesRegex(ValueError, 'image-owned redactor'):
            make_bundle('assess-0123456789abcdef', passphrase='synthetic-test-only',
                        hasher=lambda passwords: {name: '$argon2id$synthetic-test-only'
                                                  for name in passwords})

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
        project = 'sfai-assess-20261022-635651'
        args = SimpleNamespace(project_id=project,
            images_lock=str(OVERLAY / 'platform-images.lock.json'),
            control_plane_cidr='172.30.0.0/28',
            gateway_gsa=f'assess-gateway@{project}.iam.gserviceaccount.com',
            redactor_gsa=f'assess-redactor@{project}.iam.gserviceaccount.com',
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
