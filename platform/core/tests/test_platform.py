"""Offline: redaction fail-closed, provider profiles, manifest invariants (with mutations), secret separation,
front-door approvals. No cluster, no cloud, no network."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import urllib.error

from agent_platform import providers
from agent_platform.ops import approval
from agent_platform.redaction import RedactorClient
from runtime.phase3.trusted_runtime import ControlFailure

REPO = Path(__file__).resolve().parents[3]
KUBECTL = shutil.which('kubectl') or str(Path.home() / 'portfolio-sdp-us-east1-401f097/tools/kubectl')
spec = importlib.util.spec_from_file_location('render', REPO / 'platform/clouds/gke/render.py')
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


class Response(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Redaction(unittest.TestCase):
    def client(self, outcome):
        seen = []

        def opener(request, timeout=None):
            seen.append(json.loads(request.data))
            if isinstance(outcome, Exception):
                raise outcome
            return Response(outcome)
        return RedactorClient('http://redactor.platform.svc.cluster.local:4003', 'k' * 64, opener=opener), seen

    def test_redacted_text_only(self):
        client, seen = self.client({'text': 'mail [EMAIL_ADDRESS]', 'categories': ['EMAIL_ADDRESS']})
        self.assertEqual(client.redact('mail a@b.example').text, 'mail [EMAIL_ADDRESS]')
        self.assertEqual(seen, [{'text': 'mail a@b.example'}])

    def test_any_failure_blocks_the_model_request(self):
        for outcome in (urllib.error.URLError('down'), TimeoutError(), {'text': 'x'}, {'text': 'x', 'categories': ['MADE_UP']},
                        {'text': 'x', 'categories': ['PERSON', 'EMAIL_ADDRESS']}, {'text': 1, 'categories': []}, b'not json'):
            client, _ = self.client(outcome)
            with self.assertRaises(ControlFailure):
                client.redact('secret text')


class Providers(unittest.TestCase):
    def test_gemini_renders_and_is_committed(self):
        outputs = providers.render('gemini')
        config = outputs[providers.GATEWAY_CONFIG]
        self.assertIn('model: vertex_ai/gemini-3.5-flash', config)
        self.assertIn('vertex_location: us', config)
        self.assertIn('aiplatform.us.rep.googleapis.com', outputs[providers.EGRESS])
        for path, text in outputs.items():
            self.assertEqual(path.read_text(), text, 'generated file drifted: run make provider P=gemini')

    def test_inactive_unpinned_or_uncosted_profiles_refused(self):
        with self.assertRaisesRegex(providers.ProfileRejected, 'inactive'):
            providers.load('claude')
        base = providers.load('gemini')
        for mutate in (lambda p: p['model'].update(litellm_model='vertex_ai/gemini-flash-latest'),
                       lambda p: p['model'].update(input_cost_per_token=None),
                       lambda p: p['egress'].update(fqdn=['*']),
                       lambda p: p['budget'].update(monthly_usd=100)):
            profile = copy.deepcopy(base); mutate(profile)
            with self.assertRaises(providers.ProfileRejected):
                check(profile)


def check(profile):
    """Re-run load()'s validation on an in-memory profile."""
    import yaml
    path = providers.PROFILES / 'tmp-test.yaml'
    profile = dict(profile, profile='tmp-test')
    path.write_text(yaml.safe_dump(profile))
    try:
        providers.load('tmp-test')
    finally:
        path.unlink()


@unittest.skipUnless(Path(KUBECTL).exists(), 'kubectl needed for kustomize')
class Manifest(unittest.TestCase):
    ARGS = dict(project_id='example-project-123', control_plane_cidr='172.16.0.16/28',
                gateway_gsa='agent-platform-gateway@example-project-123.iam.gserviceaccount.com',
                redactor_gsa='google-sdp-runtime@example-project-123.iam.gserviceaccount.com')

    @classmethod
    def setUpClass(cls):
        import yaml
        images = json.loads((REPO / 'platform/clouds/gke/images.json').read_text())
        text, cls.refs = render.substitute(render.kustomize(KUBECTL), images=images, allow_pending=True, **cls.ARGS)
        cls.docs = [d for d in yaml.safe_load_all(text) if d]

    def mutated(self, change):
        docs = copy.deepcopy(self.docs)
        change(docs)
        return docs

    def find(self, docs, kind, name, namespace=None):
        return next(d for d in docs if d['kind'] == kind and d['metadata']['name'] == name
                    and (namespace is None or d['metadata'].get('namespace') == namespace))

    def test_rendered_manifest_holds_every_invariant(self):
        summary = render.validate(self.docs, self.refs)
        self.assertEqual(summary['kinds']['Namespace'], 3)
        self.assertNotIn('Ingress', summary['kinds'])

    def test_each_violation_is_rejected(self):
        def lb(d): self.find(d, 'Service', 'gateway')['spec']['type'] = 'LoadBalancer'
        def nodeport(d): self.find(d, 'Service', 'fault-demo')['spec']['type'] = 'NodePort'
        def no_deny(d): d.remove(self.find(d, 'NetworkPolicy', 'default-deny', 'apps'))
        def tag(d): self.find(d, 'Deployment', 'app')['spec']['template']['spec']['containers'][0]['image'] = 'nginx:latest'
        def privileged(d): self.find(d, 'Deployment', 'gateway')['spec']['template']['spec']['containers'][0]['securityContext']['privileged'] = True
        def root(d): self.find(d, 'Deployment', 'redactor')['spec']['template']['spec']['securityContext']['runAsNonRoot'] = False
        def wi_app(d): self.find(d, 'ServiceAccount', 'app')['metadata']['annotations'] = {'iam.gke.io/gcp-service-account': 'x'}
        def binding(d): d.append({'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'RoleBinding', 'metadata': {'name': 'x', 'namespace': 'apps'},
                                  'roleRef': {'kind': 'Role', 'name': 'ops-agent-observe'}, 'subjects': [{'kind': 'ServiceAccount', 'name': 'app', 'namespace': 'apps'}]})
        def cluster_role(d): d.append({'kind': 'ClusterRoleBinding', 'metadata': {'name': 'x'}})
        def secrets_read(d): self.find(d, 'Role', 'ops-agent-observe', 'apps')['rules'][0]['resources'].append('secrets')
        def wide_patch(d): self.find(d, 'Role', 'ops-agent-remediate', 'apps')['rules'][0].pop('resourceNames')
        def ingress(d): d.append({'kind': 'Ingress', 'metadata': {'name': 'x', 'namespace': 'apps'}})
        def token(d): self.find(d, 'Deployment', 'app')['spec']['template']['spec']['automountServiceAccountToken'] = True
        def pss(d): self.find(d, 'Namespace', 'ops')['metadata']['labels']['pod-security.kubernetes.io/enforce'] = 'baseline'
        def app_egress(d): d.append({'kind': 'FQDNNetworkPolicy', 'metadata': {'name': 'x', 'namespace': 'apps'}, 'spec': {}})
        for change in (lb, nodeport, no_deny, tag, privileged, root, wi_app, binding, cluster_role, secrets_read, wide_patch,
                       ingress, token, pss, app_egress):
            with self.subTest(change.__name__), self.assertRaises(render.Rejected):
                render.validate(self.mutated(change), self.refs)

    def test_registry_and_admission_share_the_same_digests(self):
        registry = self.find(self.docs, 'ConfigMap', 'ops-agent-registry', 'ops')['data']
        app_image = self.find(self.docs, 'Deployment', 'app')['spec']['template']['spec']['containers'][0]['image']
        self.assertEqual(registry['apps.app.images'], app_image)
        binding = self.find(self.docs, 'ValidatingAdmissionPolicyBinding', 'ops-agent-bounded-remediation')
        self.assertEqual(binding['spec']['paramRef'], {'name': 'ops-agent-registry', 'namespace': 'ops', 'parameterNotFoundAction': 'Deny'})
        remediate = {(r['metadata']['namespace'], n) for r in self.docs if r['kind'] == 'Role' and r['metadata']['name'] == 'ops-agent-remediate'
                     for n in r['rules'][0]['resourceNames']}
        registered = {tuple(k.split('.')[:2]) for k in registry if k.endswith('.max')}
        self.assertEqual(remediate, registered)  # RBAC names == admission parameter == agent registry

    def test_pending_images_refused_without_flag(self):
        images = json.loads((REPO / 'platform/clouds/gke/images.json').read_text())
        with self.assertRaises(render.Rejected):
            render.substitute('x', images=images, **self.ARGS)


class SecretSeparation(unittest.TestCase):
    def test_who_holds_what(self):
        from agent_platform import platform_secrets
        docs = {(d['metadata']['namespace'], d['metadata']['name']): d for d in platform_secrets.generate('correct horse battery')}
        decode = lambda d, k: __import__('base64').b64decode(d['data'][k]).decode()
        app = json.loads(decode(docs[('apps', 'app')], 'app.json'))
        ops = json.loads(decode(docs[('ops', 'ops-agent')], 'ops.json'))
        boot = json.loads(decode(docs[('platform', 'bootstrap')], 'bootstrap.json'))
        self.assertIn('PRIVATE KEY', app['approver_private_key'])
        self.assertNotIn('PRIVATE KEY', json.dumps(ops))  # the agent can verify but never sign approvals
        self.assertEqual(round(sum(k['max_budget'] for k in boot['virtual_keys']), 2), 10.0)
        self.assertNotIn('correct horse battery', json.dumps(app))
        signer = approval.Signer(app['approver_private_key'])
        proposal = {'request_id': 'r', 'target': 't', 'action': 'restart', 'args_digest': 'a', 'evidence_digest': 'e'}
        self.assertEqual(approval.Verifier(ops['approver_public_key']).consume(signer.sign(proposal), proposal)['approver'], 'owner')
        self.assertNotIn(boot['master_key'], json.dumps(app) + json.dumps(ops))
        self.assertTrue(all(d['metadata']['namespace'] in ('platform', 'apps', 'ops') for d in docs.values()))


class FrontDoorApprovals(unittest.TestCase):
    def setUp(self):
        from agent_platform import app, platform_secrets
        secret = next(d for d in platform_secrets.generate('correct horse battery') if d['metadata']['name'] == 'app')
        self.config = json.loads(__import__('base64').b64decode(secret['data']['app.json']))
        self.proposal = {'request_id': 'r1', 'target': 'apps.fault-demo', 'action': 'rollback', 'args_digest': 'a' * 64,
                         'evidence_digest': 'e' * 64}
        self.calls = []

        def opener(request, timeout=None):
            self.calls.append((request.get_method(), request.full_url, request.data and json.loads(request.data)))
            if request.full_url.endswith('/v1/snapshot'):
                return Response({'findings': {}, 'timeline': [], 'pending': [self.proposal], 'denials': []})
            return Response({'result': 'VERIFIED'})
        self.ops = app.ClusterOperations(self.config, opener=opener)

    def test_passphrase_gates_signing_and_execution_is_one_use(self):
        from runtime.agents.operations import OperationsBlocked
        with self.assertRaises(OperationsBlocked):
            self.ops.handle({'operation': 'approve', 'request_id': 'r1', 'operator_secret': 'wrong passphrase'})
        granted = self.ops.handle({'operation': 'approve', 'request_id': 'r1', 'operator_secret': 'correct horse battery'})
        result = self.ops.handle({'operation': 'execute', 'request_id': 'r1', 'approval_id': granted['approval_id']})
        self.assertEqual(result, {'result': 'VERIFIED'})
        token = self.calls[-1][2]['approval']
        self.assertNotIn(token, json.dumps(granted))  # the browser never sees the signed token
        with self.assertRaises(OperationsBlocked):
            self.ops.handle({'operation': 'execute', 'request_id': 'r1', 'approval_id': granted['approval_id']})


if __name__ == '__main__':
    unittest.main()


class DashboardAssets(unittest.TestCase):
    """No JS engine offline: static invariants of the platform dashboard overlay."""

    def test_safe_bilingual_dashboard(self):
        script = (REPO / 'platform/core/ui/operations.js').read_text()
        html = (REPO / 'platform/core/ui/operations.html').read_text()
        self.assertNotIn('innerHTML', script)
        self.assertIn("lang === 'ar' ? 'rtl' : 'ltr'", script)
        for label in ('نشاط الوكيل', 'موافقات معلّقة', 'حالات الرفض بالسياسة', 'Rollback to previous revision'):
            self.assertIn(label, script)
        for element in ('activity', 'pending', 'timeline', 'denials'):
            self.assertIn('id="' + element + '"', html)
            self.assertIn("'" + element + "'", script)
        for open_, close in ('()', '[]', '{}'):
            self.assertEqual(script.count(open_), script.count(close), open_ + close)
        self.assertLessEqual(len(script.encode()), 16384)  # read_fixed limit of the UI server
