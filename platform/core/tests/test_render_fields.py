"""Full offline render: substitutions must not rewrite identifiers or executable ConfigMap data."""
import importlib.util
import json
from pathlib import Path
import shutil
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
PROJECT = 'render-fixture'
GATEWAY_GSA = 'fixture-gateway@' + PROJECT + '.iam.gserviceaccount.com'
REDACTOR_GSA = 'fixture-redactor@' + PROJECT + '.iam.gserviceaccount.com'
spec = importlib.util.spec_from_file_location('render_fields', ROOT / 'platform/clouds/gke/render.py')
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


class RenderFields(unittest.TestCase):
    def test_literal_placeholders_are_not_rewritten_in_other_fields(self):
        lock = {'registry': 'us-east1-docker.pkg.dev/render-fixture/images/',
                'images': {name: name + '@sha256:' + 'a' * 64 for name in render.IMAGE_NAMES}}
        source = yaml.safe_dump({'data': {'program.py': "print('PROJECT_ID')\n",
                                         'literal': 'PROJECT_ID', 'PORTFOLIO_PROJECT_ID': 'unchanged'},
                                 'env': [{'name': 'PROJECT_ID', 'value': 'literal'}],
                                 'annotations': {'iam.gke.io/gcp-service-account': 'GATEWAY_GSA'},
                                 'project_id': 'PROJECT_ID', 'cidr': 'CONTROL_PLANE_CIDR'})
        text, _ = render.substitute(source, project_id='render-fixture', control_plane_cidr='172.16.0.16/28',
                                   gateway_gsa=GATEWAY_GSA, redactor_gsa=REDACTOR_GSA, images=lock)
        doc = yaml.safe_load(text)
        self.assertEqual(doc['data'], yaml.safe_load(source)['data'])
        self.assertEqual(doc['env'][0]['name'], 'PROJECT_ID')
        self.assertEqual(doc['project_id'], 'render-fixture')
        self.assertEqual(doc['cidr'], '172.16.0.16/28')
        self.assertEqual(doc['annotations']['iam.gke.io/gcp-service-account'],
                         GATEWAY_GSA)

    def test_full_render_has_image_owned_programs_and_resolves_declared_values(self):
        source = render.kustomize(shutil.which('kubectl') or 'kubectl')
        lock = json.loads((ROOT / 'platform/clouds/gke/release-rc1.lock.json').read_text())
        lock['registry'] = lock['registry'].replace('PROJECT_ID', 'render-fixture')
        text, refs = render.substitute(source, project_id='render-fixture', control_plane_cidr='172.16.0.16/28',
                                       gateway_gsa=GATEWAY_GSA, redactor_gsa=REDACTOR_GSA, images=lock)
        before, after = list(yaml.safe_load_all(source)), list(yaml.safe_load_all(text))
        from agent_platform import onboarding, release_facts
        release_facts.install(after, onboarding.load_all(), lock, private_values=(PROJECT,))
        render.validate(after, refs)
        original = {d['metadata']['name']: d['data'] for d in before if d['kind'] == 'ConfigMap'
                    and d['metadata']['name'].startswith('gateway-config-')}
        for doc in after:
            if doc['kind'] == 'ConfigMap' and doc['metadata']['name'] in original:
                self.assertEqual(doc['data'], original[doc['metadata']['name']])
        assert not any(d['kind'] == 'ConfigMap' and d['metadata']['name'].startswith(
            ('platform-programs-', 'database-sql-')) for d in after)
        assert set(next(d for d in after if d['kind'] == 'ConfigMap' and
            d['metadata']['name'].startswith('gateway-config-'))['data']) == {'litellm.yaml'}
        env = [e['name'] for d in after if d['kind'] == 'Deployment'
               for c in d['spec']['template']['spec']['containers'] for e in c.get('env', [])]
        self.assertEqual(env.count('PORTFOLIO_PROJECT_ID'), 2)
        settings = next(d for d in after if d['kind'] == 'ConfigMap' and d['metadata']['name'] == 'platform-settings')
        self.assertEqual(settings['data']['project_id'], 'render-fixture')
        self.assertNotIn('PORTFOLIO_render-fixture', text)
        unresolved = next(d for d in after if d['kind'] == 'ConfigMap' and d['metadata']['name'] == 'platform-settings')
        unresolved['data']['project_id'] = 'PROJECT_ID'
        with self.assertRaises(render.Rejected):
            render.validate(after, refs)


if __name__ == '__main__':
    unittest.main()
