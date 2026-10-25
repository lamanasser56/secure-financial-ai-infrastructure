"""Current full Kustomize RBAC must match the single declared authority; drift fails closed."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import shutil
import unittest

import yaml

from agent_platform import onboarding
from agent_platform.ops import authority, posture

ROOT = Path(__file__).resolve().parents[3]


class RenderedClient:
    def __init__(self, docs):
        self.docs = deepcopy(docs)

    def list(self, kind, namespace):
        kinds = {'roles': 'Role', 'rolebindings': 'RoleBinding', 'networkpolicies': 'NetworkPolicy', 'pods': 'Pod', 'events': 'Event'}
        return [doc for doc in self.docs if doc['kind'] == kinds[kind] and doc['metadata'].get('namespace') == namespace]


class Authority(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('authority_render', ROOT / 'platform/clouds/gke/render.py')
        render = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(render)
        cls.docs = list(yaml.safe_load_all(render.kustomize(shutil.which('kubectl') or 'kubectl')))
        cls.workloads = {d['metadata']['namespace']: [] for d in cls.docs if d['kind'] == 'RoleBinding'}
        for doc in cls.docs:
            if doc['kind'] == 'Deployment' and doc['metadata']['namespace'] in cls.workloads:
                cls.workloads[doc['metadata']['namespace']].append(doc['metadata']['name'])

    def check(self, client):
        return posture.check(client, sorted(self.workloads), self.workloads)

    def test_current_rendered_rbac_has_no_false_findings(self):
        result = self.check(RenderedClient(self.docs))
        self.assertEqual(result['findings'], [])
        self.assertTrue(result['clean'])

    def test_generated_sources_have_one_owner(self):
        self.assertEqual((ROOT / 'platform/core/kubernetes/policies/ops-agent-rbac.yaml').read_text(), authority.core_manifest())
        manifests, expected = onboarding.outputs()
        for path, text in expected.items():
            self.assertEqual(path.read_text(), text)

    def test_binding_role_reference_and_subjects_are_exact(self):
        original = next(d for d in self.docs if d['kind'] == 'RoleBinding' and d['metadata']['name'] == 'ops-agent-remediate')
        mutations = [
            lambda b: b['subjects'].append({'kind': 'ServiceAccount', 'name': 'outsider', 'namespace': 'ops'}),
            lambda b: b['subjects'].append(deepcopy(b['subjects'][0])),
            lambda b: b['subjects'][0].update(namespace='apps'),
            lambda b: b['subjects'][0].update(name='ops-agent'),
            lambda b: b['subjects'][0].update(kind='User'),
            lambda b: b.update(subjects=[]),
            lambda b: b['roleRef'].update(name='different-role'),
            lambda b: b['roleRef'].update(kind='ClusterRole'),
            lambda b: b['roleRef'].update(apiGroup='different.example'),
            lambda b: b['metadata'].update(name='extra-binding'),
        ]
        for mutate in mutations:
            client = RenderedClient(self.docs)
            changed = next(d for d in client.docs if d == original)
            mutate(changed)
            with self.subTest(mutate=mutations.index(mutate)):
                found = self.check(client)
                self.assertFalse(found['clean'])
                self.assertIn('UNEXPECTED_ROLE_BINDING', {f['finding'] for f in found['findings']})

    def test_extra_empty_binding_and_extra_privileges_are_rejected(self):
        client = RenderedClient(self.docs)
        client.docs.append({'kind': 'RoleBinding', 'metadata': {'namespace': 'apps', 'name': 'empty-extra'},
                            'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': 'ops-agent-observe'},
                            'subjects': []})
        role = next(d for d in client.docs if d['kind'] == 'Role' and d['metadata']['namespace'] == 'apps')
        role['rules'].append({'apiGroups': [''], 'resources': ['secrets'], 'verbs': ['get']})
        found = {f['finding'] for f in self.check(client)['findings']}
        self.assertTrue({'UNEXPECTED_ROLE_BINDING', 'UNEXPECTED_ROLE'} <= found)

    def test_missing_authority_is_not_clean(self):
        client = RenderedClient([d for d in self.docs if d['kind'] != 'RoleBinding'])
        self.assertIn('MISSING_ROLE_BINDING', {f['finding'] for f in self.check(client)['findings']})

    def test_kubernetes_empty_subject_apigroup_is_equivalent_but_other_fields_are_not(self):
        client = RenderedClient(self.docs)
        for doc in client.docs:
            if doc['kind'] == 'RoleBinding':
                for subject in doc['subjects']:
                    subject['apiGroup'] = ''
        self.assertTrue(self.check(client)['clean'])
        binding = next(d for d in client.docs if d['kind'] == 'RoleBinding')
        binding['subjects'][0]['unexpected'] = 'value'
        self.assertFalse(self.check(client)['clean'])


if __name__ == '__main__':
    unittest.main()
