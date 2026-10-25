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
APP = ('us-east1-docker.pkg.dev/project-b1e55144-cfd4-4fef-89a/'
       'sdp-evaluation-images/agent-platform-app@sha256:'
       'dbbe22b5628bda3fd1f9b41f92a69abcdf7a583871fff1615e1708356e4b467c')


class LiveToolingTest(unittest.TestCase):
    def test_full_disposable_bundle_restores_main_source_and_stages_fail_closed(self):
        docs, receipt = make_bundle('assess-0123456789abcdef', passphrase='synthetic-test-only',
            hasher=lambda passwords: {name: '$argon2id$synthetic-test-only'
                                      for name in passwords})
        self.assertEqual(receipt['objects'], 143)
        self.assertFalse(receipt['external_llm_route'])
        self.assertEqual(len(receipt['restored_main_environment_names']), 2)
        self.assertEqual([len(s) for s in split(docs)], [22, 103, 1, 1, 1, 2, 13])
        programs = next(d for d in docs if d['kind'] == 'ConfigMap' and
            d['metadata']['name'].startswith('platform-programs-'))['data']
        expected = (ROOT / 'platform/core/src/agent_platform/programs/redactor_server.py').read_text()
        self.assertEqual(programs['redactor_server.py'].replace('\r\n', '\n'), expected.replace('\r\n', '\n'))
        self.assertNotIn('PORTFOLIO_sfai-assess-20261022-635651', json.dumps(docs))
        self.assertNotIn('vertex_ai/', json.dumps(docs))

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
        args = SimpleNamespace(project_id='sfai-assess-20261022-635651',
            images_lock=str(OVERLAY / 'platform-images.lock.json'),
            control_plane_cidr='172.30.0.0/28',
            gateway_gsa='assess-gateway@sfai-assess-20261022-635651.iam.gserviceaccount.com',
            redactor_gsa='assess-redactor@sfai-assess-20261022-635651.iam.gserviceaccount.com',
            kubectl='kubectl')
        rendered, summary = module.render(args)
        self.assertEqual(summary['objects'], 113)
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
        before_programs = find('ConfigMap', 'platform', 'platform-programs-')[0]
        source_programs = next(d for d in original if d['kind'] == 'ConfigMap' and
                               d['metadata']['name'].startswith('platform-programs-'))
        self.assertEqual(before_programs['data'], source_programs['data'])


if __name__ == '__main__':
    unittest.main()
