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


class RedactionWindow(unittest.TestCase):
    def test_budget_renews_every_window_and_fails_as_a_runtime_stage(self):
        from agent_platform.redaction import WindowedBoundaryBudget
        now = [0.0]
        budget = WindowedBoundaryBudget(operations=2, clock=lambda: now[0])
        budget.reserve('a'); budget.reserve('b')
        with self.assertRaises(ControlFailure):
            budget.reserve('c')  # per-window limit still holds
        now[0] = 901.0  # past the core's 900 s maximum lifetime: a fresh window, same limits
        budget.reserve('d')
        self.assertEqual(budget.operations, 1)
        client = RedactorClient('http://redactor.invalid:4003', 'k' * 64, budget=budget,
                                opener=lambda *a, **k: Response(json.dumps({'text': 'x', 'categories': []}).encode()))
        client.redact('e')
        with self.assertRaises(ControlFailure) as failure:
            client.redact('f')
        self.assertEqual((failure.exception.stage, failure.exception.category), ('presidio_anonymizer', 'unavailable'))


class Providers(unittest.TestCase):
    def test_gemini_renders_and_is_committed(self):
        outputs = providers.render('gemini')
        config = outputs[providers.GATEWAY_CONFIG]
        self.assertIn('model: vertex_ai/gemini-3.5-flash', config)
        self.assertIn('vertex_location: us', config)
        self.assertIn('reasoning_effort: low', config)  # thought text is removed by the gateway hook
        self.assertIn('max_tokens: 1024', config)
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
                       lambda p: p['budget'].update(monthly_usd=100),
                       lambda p: p['model'].update(reasoning_effort='medium'),  # beyond the approved levels
                       lambda p: p['model'].update(reasoning_effort='high'),
                       lambda p: p['model']['limits'].update(max_tokens=2048)):
            profile = copy.deepcopy(base); mutate(profile)
            with self.assertRaises(providers.ProfileRejected):
                check(profile)


class Explanation(unittest.TestCase):
    """Ops explanations request the profile ceiling and never show a truncated or empty answer."""
    FINDING = {'deployment': 'demo', 'namespace': 'apps', 'finding': 'CRASH_LOOP', 'evidence': {}, 'suggested_actions': []}

    def explain(self, choice):
        from agent_platform.ops.explain import Explainer
        sent = []

        class Redactor:
            def redact(self, value):
                return type('R', (), {'text': value})()

        def opener(request, timeout):
            sent.append(json.loads(request.data))
            return Response({'choices': [choice]})
        return Explainer('http://gateway.invalid:4000', 'k', Redactor(), opener=opener)(self.FINDING), sent

    def test_complete_answer_is_shown(self):
        result, sent = self.explain({'finish_reason': 'stop', 'message': {'content': 'Pod restarts.'}})
        self.assertEqual(result, {'untrusted_text': 'Pod restarts.', 'untrusted_text_ar': None, 'source': 'model_via_gateway'})
        self.assertEqual(sent[0]['max_tokens'], providers.MAX_TOKENS)

    def test_one_call_returns_english_and_arabic(self):
        reply = json.dumps({'en': 'The Pod keeps restarting.', 'ar': 'الـ Pod يُعاد تشغيله باستمرار.'}, ensure_ascii=False)
        result, sent = self.explain({'finish_reason': 'stop', 'message': {'content': reply}})
        self.assertEqual(len(sent), 1)  # still one model request per incident
        self.assertEqual(sent[0]['response_format'], {'type': 'json_object'})
        self.assertEqual(sent[0]['timeout'], 20)  # this call only; the provider profile keeps 8 s
        self.assertEqual((result['untrusted_text'], result['untrusted_text_ar']), ('The Pod keeps restarting.', 'الـ Pod يُعاد تشغيله باستمرار.'))
        for bad in (json.dumps({'ar': 'فقط'}), json.dumps(['x']), json.dumps({'en': ' '})):
            with self.subTest(bad=bad):
                self.assertEqual(self.explain({'finish_reason': 'stop', 'message': {'content': bad}})[0]['source'], 'unavailable')

    def test_truncated_or_empty_answer_is_unavailable(self):
        for choice in ({'finish_reason': 'length', 'message': {'content': 'Pod rest'}},
                       {'finish_reason': 'stop', 'message': {'content': None}},
                       {'finish_reason': 'stop', 'message': {'content': ' '}}):
            self.assertEqual(self.explain(choice)[0], {'untrusted_text': None, 'untrusted_text_ar': None, 'source': 'unavailable'})


class FaultDemoWedge(unittest.TestCase):
    """`make fault F=wedge`: loopback-only trigger; readiness fails until a new Pod (rollout restart) replaces it."""

    def test_wedge_is_loopback_only_and_fails_readiness(self):
        import threading
        from http.server import HTTPServer
        from agent_platform.programs import fault_demo
        server = HTTPServer(('127.0.0.1', 0), fault_demo.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % server.server_address[1]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def status(path, method='GET'):
            try:
                return opener.open(urllib.request.Request(base + path, method=method), timeout=5).status
            except urllib.error.HTTPError as error:
                return error.code
        try:
            self.assertEqual(status('/healthz'), 200)
            self.assertEqual(status('/other', 'POST'), 403)
            self.assertEqual(status('/wedge', 'POST'), 204)
            self.assertEqual(status('/healthz'), 503)
        finally:
            server.shutdown()
            fault_demo.Handler.wedged = False


class PlatformInstruction(unittest.TestCase):
    """The platform instruction reaches the system message only and names every free-text decision field."""

    def test_system_message_only(self):
        from agent_platform import app
        sent = []
        payload = {'model': 'secure-financial-chat', 'max_tokens': 1024,
                   'messages': [{'role': 'system', 'content': 'core rule'}, {'role': 'user', 'content': 'redacted'}]}
        app.instructed(lambda url, body, timeout, headers: sent.append(body) or 'ok')('u', payload, 8, {})
        self.assertEqual(sent[0]['messages'], [{'role': 'system', 'content': 'core rule ' + app.PLATFORM_INSTRUCTION},
                                               {'role': 'user', 'content': 'redacted'}])
        self.assertEqual(payload['messages'][0]['content'], 'core rule')  # the core's payload is not mutated
        self.assertEqual(sent[0]['max_tokens'], 1024)
        with self.assertRaises(ValueError):
            app.instructed(lambda *a: None)('u', {'messages': [{'role': 'user', 'content': 'x'}]}, 8, {})

    def test_names_every_required_free_text_field(self):
        from agent_platform import app
        schema = json.loads((REPO / 'contracts/agents/decision.schema.json').read_text())
        free_text = {name for branch in schema['oneOf'] for name in branch['required']
                     if branch['properties'][name].get('type') == 'string' and 'pattern' not in branch['properties'][name]}
        self.assertEqual(free_text, {'summary', 'limitations', 'observed_failure', 'suspected_cause', 'proposed_repair'})
        for name in free_text:
            self.assertIn(name, app.PLATFORM_INSTRUCTION)

    def test_states_every_core_precondition(self):
        """Each precondition the qualified core enforces before accepting a decision is stated in the instruction."""
        from agent_platform import app
        from runtime.agents.controls import PROFILES
        rule = app.PLATFORM_INSTRUCTION
        schema = json.loads((REPO / 'contracts/agents/decision.schema.json').read_text())
        # envelope (protocol_preparation.canonical_decision): exactly summary + classification, closed values
        self.assertIn('exactly two keys: summary', rule)
        for value in ('informational', 'action_required'):
            self.assertIn(value, rule)
        # tool step: closed fields, listed tools only, once each, summary before categories (core.py authorization)
        tool = next(b for b in schema['oneOf'] if b['properties']['kind'] == {'const': 'tool'})
        self.assertIn('{kind:tool,tool_id,arguments}', rule)
        self.assertEqual(set(tool['required']), {'kind', 'tool_id', 'arguments'})
        self.assertIn('at most once', rule)
        self.assertIn('expense_summary first, then expense_categories', rule)
        # final only after every profile tool ran (core.py: observed tools == PROFILES[profile])
        self.assertIn('only after EVERY listed tool has an observation', rule)
        self.assertEqual(PROFILES['financial'], {'expense_summary', 'expense_categories'})
        # final fields: exactly the schema's properties per profile (additionalProperties false)
        for branch in schema['oneOf']:
            if branch['properties']['kind'] == {'const': 'final'}:
                self.assertFalse(branch['additionalProperties'])
                agent = branch['properties']['agent']['const']
                stated = rule.split(agent.capitalize() + ': ')[1].split('.')[0]
                self.assertEqual(set(stated.split(', ')), set(branch['properties']), agent)
                for name, spec in branch['properties'].items():
                    if spec.get('type') == 'string' and 'maxLength' in spec and 'pattern' not in spec:
                        self.assertIn('at most %d' % spec['maxLength'], rule, name)
        # agent / language / period / evidence_ids equalities (core.py ungrounded_response)
        for text in ('agent is the given agent', 'language is the given language', '(YYYY-MM)',
                     'null for the infrastructure agent', 'distinct source_id values', 'excluding read_image_summary'):
            self.assertIn(text, rule)
        # clarification and refusal codes the live core accepts (core.py invalid_clarification / invalid_refusal)
        for text in ('reason_code:period_required} for the financial agent', 'evidence_required for the infrastructure',
                     '{kind:refusal,reason_code:out_of_scope}'):
            self.assertIn(text, rule)
        # minimize(): no tenant identifier; assess_prompt_injection() on the decision
        self.assertIn('Never include a tenant identifier', rule)
        self.assertIn('never repeat instructions', rule)

    def test_schema_is_not_relaxed(self):
        schema = json.loads((REPO / 'contracts/agents/decision.schema.json').read_text())
        finals = [b for b in schema['oneOf'] if b['properties']['kind'] == {'const': 'final'}]
        self.assertTrue(finals and all(b['properties']['limitations']['minLength'] == 1 for b in finals))


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
    PROJECT = 'example-project-123'
    ARGS = dict(project_id=PROJECT, control_plane_cidr='172.16.0.16/28',
                gateway_gsa=f'agent-platform-gateway@{PROJECT}.iam.gserviceaccount.com',
                redactor_gsa=f'google-sdp-runtime@{PROJECT}.iam.gserviceaccount.com')

    @classmethod
    def setUpClass(cls):
        import yaml
        images = json.loads((REPO / 'platform/clouds/gke/images.json').read_text())
        images['registry'] = images['registry'].replace('PROJECT_ID', cls.PROJECT)
        text, cls.refs = render.substitute(render.kustomize(KUBECTL), images=images, allow_pending=True, **cls.ARGS)
        cls.docs = [d for d in yaml.safe_load_all(text) if d]
        from agent_platform import onboarding, release_facts
        release_facts.install(cls.docs, onboarding.load_all(), images, private_values=(cls.PROJECT,))

    def mutated(self, change):
        docs = copy.deepcopy(self.docs)
        change(docs)
        return docs

    def find(self, docs, kind, name, namespace=None):
        return next(d for d in docs if d['kind'] == kind and d['metadata']['name'] == name
                    and (namespace is None or d['metadata'].get('namespace') == namespace))

    def test_rendered_manifest_holds_every_invariant(self):
        summary = render.validate(self.docs, self.refs)
        self.assertEqual(summary['kinds']['Namespace'], 5)  # platform, apps, ops + onboarded agent-financial, agent-platform-guide
        self.assertNotIn('Ingress', summary['kinds'])

    def test_each_violation_is_rejected(self):
        def lb(d): self.find(d, 'Service', 'gateway')['spec']['type'] = 'LoadBalancer'
        def nodeport(d): self.find(d, 'Service', 'fault-demo')['spec']['type'] = 'NodePort'
        def agent_internet(d): self.find(d, 'NetworkPolicy', 'agent', 'agent-financial')['spec']['egress'].append({'to': [{'ipBlock': {'cidr': '0.0.0.0/0'}}]})
        def agent_rbac(d): d.append({'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'Role', 'metadata': {'name': 'x', 'namespace': 'agent-financial'},
                                     'rules': [{'apiGroups': [''], 'resources': ['pods'], 'verbs': ['get']}]})
        def agent_quota(d): d.remove(self.find(d, 'ResourceQuota', 'bounds', 'agent-financial'))
        def agent_extra_policy(d): d.append({'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'metadata': {'name': 'open', 'namespace': 'agent-financial'},
                                             'spec': {'podSelector': {}, 'egress': [{}], 'policyTypes': ['Egress']}})
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
                       ingress, token, pss, app_egress, agent_internet, agent_rbac, agent_quota, agent_extra_policy):
            with self.subTest(change.__name__), self.assertRaises(render.Rejected):
                render.validate(self.mutated(change), self.refs)

    def test_registry_and_admission_share_the_same_digests(self):
        registry = self.find(self.docs, 'ConfigMap', 'ops-agent-registry', 'ops')['data']
        app_image = self.find(self.docs, 'Deployment', 'app')['spec']['template']['spec']['containers'][0]['image']
        self.assertNotIn('IMAGE:', json.dumps(registry))
        self.assertFalse([k for k in registry if k.endswith('.images')])  # no rollback: the agent never selects an image
        self.assertTrue(app_image.startswith('us-east1-docker.pkg.dev/'))
        binding = self.find(self.docs, 'ValidatingAdmissionPolicyBinding', 'ops-agent-bounded-remediation')
        self.assertEqual(binding['spec']['paramRef'], {'name': 'ops-agent-registry', 'namespace': 'ops', 'parameterNotFoundAction': 'Deny'})
        remediate = {(r['metadata']['namespace'], n) for r in self.docs if r['kind'] == 'Role' and r['metadata']['name'] == 'ops-agent-remediate'
                     for n in r['rules'][0]['resourceNames']}
        registered = {tuple(k.split('.')[:2]) for k in registry if k.endswith('.max')}
        self.assertEqual(remediate, registered)  # RBAC names == admission parameter == agent registry

    def test_pending_images_refused_without_flag(self):
        images = json.loads((REPO / 'platform/clouds/gke/images.json').read_text())
        images['images']['app'] = 'PENDING_CI'  # an image whose CI publication has not happened yet
        with self.assertRaises(render.Rejected):
            render.substitute('x', images=images, **self.ARGS)


class SecretSeparation(unittest.TestCase):
    def test_who_holds_what(self):
        from agent_platform import platform_secrets
        docs = {(d['metadata']['namespace'], d['metadata']['name']): d for d in platform_secrets.generate('correct horse battery', hasher=lambda pw: {u: '$argon2id$fake' for u in pw})}
        decode = lambda d, k: __import__('base64').b64decode(d['data'][k]).decode()
        app = json.loads(decode(docs[('apps', 'app')], 'app.json'))
        ops = json.loads(decode(docs[('ops', 'ops-agent')], 'ops.json'))
        boot = json.loads(decode(docs[('platform', 'bootstrap')], 'bootstrap.json'))
        self.assertIn('PRIVATE KEY', app['approver_private_key'])
        self.assertNotIn('PRIVATE KEY', json.dumps(ops))  # the agent can verify but never sign approvals
        self.assertEqual(round(sum(k['max_budget'] for k in boot['virtual_keys']), 2), 10.0)  # at the $10 ceiling, never above
        self.assertNotIn('correct horse battery', json.dumps(app))
        signer = approval.Signer(app['approver_private_key'])
        proposal = {'request_id': 'r', 'target': 't', 'action': 'restart', 'args_digest': 'a', 'evidence_digest': 'e',
                    'uid': 'u', 'resource_version': '1'}
        self.assertEqual(approval.Verifier(ops['approver_public_key']).consume(signer.sign(proposal), proposal)['approver'], 'owner')
        self.assertNotIn(boot['master_key'], json.dumps(app) + json.dumps(ops))
        self.assertTrue(all(d['metadata']['namespace'] in ('platform', 'apps', 'ops', 'agent-financial', 'agent-platform-guide') for d in docs.values()))
        # an onboarded agent holds its own gateway key and its own redactor key (and never the master key)
        financial = json.loads(decode(docs[('agent-financial', 'agent-u1')], 'agent.json'))
        clients = json.loads(decode(docs[('platform', 'redactor')], 'clients.json'))
        keys = {k['alias'].removeprefix('boundary-'): k for k in boot['virtual_keys']}
        boundary = json.loads(decode(docs[('platform', 'gateway-boundary')], 'boundary.json'))
        self.assertEqual((financial['gateway_key'], financial['redactor_key']),
                         (boundary['clients']['agent-financial']['external_key'], clients['agent-financial']))
        self.assertEqual((keys['agent-financial']['max_budget'], keys['app-infrastructure']['max_budget']), (5.0, 2.5))
        self.assertNotIn(boot['master_key'], json.dumps(financial))
        self.assertEqual(app['client_keys']['financial'], boundary['clients']['app-financial']['external_key'])
        self.assertNotEqual(financial['gateway_key'], keys['agent-financial']['key'])


class FrontDoorApprovals(unittest.TestCase):
    def setUp(self):
        from agent_platform import app, platform_secrets
        secret = next(d for d in platform_secrets.generate('correct horse battery', hasher=lambda pw: {u: '$argon2id$fake' for u in pw}) if d['metadata']['name'] == 'app')
        self.config = json.loads(__import__('base64').b64decode(secret['data']['app.json']))
        self.proposal = {'request_id': 'r1', 'target': 'apps.fault-demo', 'action': 'restart', 'args_digest': 'a' * 64,
                         'evidence_digest': 'e' * 64, 'uid': 'uid-1', 'resource_version': '100'}
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

    def refusal(self, request, ops=None):
        """Run one request that must be refused; return (user-facing code, audit line, raw audit text)."""
        import contextlib
        import io
        from runtime.agents.operations import OperationsBlocked
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(OperationsBlocked) as raised:
            (ops or self.ops).handle(request)
        lines = [json.loads(line) for line in out.getvalue().splitlines() if 'ops_approval_refused' in line]
        self.assertEqual(len(lines), 1)
        return raised.exception.code, lines[0], out.getvalue()

    def test_refused_approval_records_the_precise_reason_and_the_user_message_stays_generic(self):
        wrong = {'operation': 'approve', 'operator_secret': 'wrong passphrase'}
        right = {'operation': 'approve', 'operator_secret': 'correct horse battery'}
        cases = (
            (dict(wrong, request_id='r1'), 'passphrase_mismatch', True),    # proposal is pending, passphrase is wrong
            (dict(wrong, request_id='gone'), 'passphrase_mismatch', False),  # both wrong: the passphrase is reported
            (dict(right, request_id='gone'), 'not_pending', False),         # newer proposal, expired or executed
        )
        for request, reason, pending in cases:
            with self.subTest(reason=reason, pending=pending, request_id=request['request_id']):
                code, line, raw = self.refusal(request)
                self.assertEqual(code, 'APPROVAL_DENIED')  # the same safe message for every cause
                self.assertEqual((line['reason'], line['stage'], line['proposal_pending']), (reason, 'approve', pending))
                self.assertEqual(line['request_id'], request['request_id'])
                for secret in ('wrong passphrase', 'correct horse battery'):
                    self.assertNotIn(secret, raw)  # the submitted passphrase is never logged, whole or in part

    def test_refused_execution_records_which_check_failed(self):
        granted = self.ops.handle({'operation': 'approve', 'request_id': 'r1', 'operator_secret': 'correct horse battery'})
        base = {'operation': 'execute'}
        for request, reason in ((dict(base, request_id='r1', approval_id='unknown'), 'approval_unknown_or_used'),
                                (dict(base, request_id='other', approval_id=granted['approval_id']), 'request_mismatch')):
            with self.subTest(reason=reason):
                code, line, _ = self.refusal(request)
                self.assertEqual((code, line['reason'], line['stage']), ('APPROVAL_DENIED', reason, 'execute'))

    def test_overview_board_carries_the_ops_agents_explanation_as_display_text_only(self):
        from agent_platform import app
        finding = {'finding': 'CRASH_LOOP', 'desired_replicas': 1, 'available_replicas': 0, 'evidence': [],
                   'explanation': {'untrusted_text': 'The workload exits on start.', 'untrusted_text_ar': None, 'source': 'model_via_gateway'}}
        ops = app.ClusterOperations(self.config, opener=lambda request, timeout=None: Response(
            {'findings': {'apps.fault-demo': finding, 'platform.gateway': dict(finding, finding='HEALTHY', explanation=None)},
             'timeline': [], 'pending': [], 'denials': []}))
        board = {b['target_id']: b for b in ops.handle({'operation': 'overview'})['board']}
        self.assertEqual(board['apps.fault-demo']['explanation'], 'The workload exits on start.')
        self.assertIsNone(board['platform.gateway']['explanation'])

    def test_expired_approval_is_recorded_as_expired(self):
        from agent_platform import app
        now = [1000.0]
        ops = app.ClusterOperations(self.config, opener=lambda request, timeout=None: Response(
            {'findings': {}, 'timeline': [], 'pending': [self.proposal], 'denials': []}), clock=lambda: now[0])
        granted = ops.handle({'operation': 'approve', 'request_id': 'r1', 'operator_secret': 'correct horse battery'})
        now[0] += 301
        code, line, _ = self.refusal({'operation': 'execute', 'request_id': 'r1', 'approval_id': granted['approval_id']}, ops)
        self.assertEqual((code, line['reason']), ('APPROVAL_DENIED', 'approval_expired'))

    def test_client_supplied_request_id_is_not_logged_verbatim(self):
        _, line, raw = self.refusal({'operation': 'approve', 'request_id': 'x' * 200 + ' <script>',
                                     'operator_secret': 'wrong passphrase'})
        self.assertIsNone(line['request_id'])
        self.assertNotIn('<script>', raw)


if __name__ == '__main__':
    unittest.main()


class ModelResponseAdmission(unittest.TestCase):
    """Gemini 3.x via LiteLLM 1.104.0: the gateway hook removes the opaque thought signature; the core admission decides."""
    SECRET = 'Tenant secret answer text'
    ENVELOPE = json.dumps({'summary': json.dumps({'kind': 'tool', 'tool_id': 'expense_summary', 'arguments': {'period': '2026-02'}}),
                           'classification': 'informational'})

    def reply(self, **message):
        base = {'role': 'assistant', 'content': self.ENVELOPE}
        base.update(message)
        return {'choices': [{'index': 0, 'finish_reason': 'stop', 'message': base}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15,
                          'completion_tokens_details': {'reasoning_tokens': 3}}}

    def test_signature_reaching_the_app_is_rejected(self):
        from runtime.agents.protocol_preparation import completion_content
        with self.assertRaises(ControlFailure):  # fail closed if the gateway hook were ever bypassed
            completion_content(self.reply(provider_specific_fields={'thought_signatures': ['b3BhcXVl']}))

    @unittest.skipUnless(importlib.util.find_spec('litellm'), 'litellm needed for the gateway hook')
    def test_gateway_hook_on_real_litellm_types(self):
        import asyncio
        from litellm.types.utils import Choices, Message, ModelResponse
        from runtime.agents.protocol_preparation import completion_content
        sys.path.insert(0, str(REPO / 'platform/core/src/agent_platform/programs'))
        import gateway_hooks

        def gemini(fields, thinking=()):
            message = Message(role='assistant', content=self.ENVELOPE, provider_specific_fields=fields,
                              thinking_blocks=list(thinking))
            message.images = []  # LiteLLM 1.104.0 sets both placeholders on every Gemini reply (live, 2026-10-10)
            return ModelResponse(choices=[Choices(index=0, finish_reason='stop', message=message)])
        response = gemini({'thought_signatures': ['b3BhcXVl']})
        returned = asyncio.run(gateway_hooks.thought_signature_boundary.async_post_call_success_hook({}, None, response))
        wire = json.loads(returned.model_dump_json())  # what the proxy sends to the app
        self.assertNotIn('b3BhcXVl', json.dumps(wire))
        self.assertEqual(completion_content(wire), self.ENVELOPE)
        other = gemini({'thought_signatures': ['b3BhcXVl'], 'other': 1})
        gateway_hooks.strip_thought_signatures(other)
        with self.assertRaises(ControlFailure):  # anything else still reaches the core admission and is rejected
            completion_content(json.loads(other.model_dump_json()))
        thought = gemini({'thought_signatures': ['b3BhcXVl']}, [{'type': 'thinking', 'thinking': self.SECRET}])
        thought.choices[0].message.reasoning_content = self.SECRET
        unstripped = json.loads(thought.model_dump_json())
        with self.assertRaises(ControlFailure):  # thought text is never admitted if the hook were ever bypassed
            completion_content(unstripped)
        returned = asyncio.run(gateway_hooks.thought_signature_boundary.async_post_call_success_hook({}, None, thought))
        wire = json.loads(returned.model_dump_json())  # reasoning_effort low: thought text stays in the gateway
        self.assertNotIn(self.SECRET, json.dumps(wire))
        self.assertEqual(completion_content(wire), self.ENVELOPE)
        image = gemini({})
        image.choices[0].message.images = [{'type': 'image_url', 'image_url': {'url': 'data:,'}}]
        gateway_hooks.strip_thought_signatures(image)
        with self.assertRaises(ControlFailure):  # a real image still reaches the core admission
            completion_content(json.loads(image.model_dump_json()))

    def test_every_model_request_is_stateless(self):
        """No model turn is ever replayed to the provider, so no thought signature round-trip exists."""
        from runtime.agents.composition import ProtocolHTTPGateway
        from runtime.phase3.trusted_runtime import RedactionResult
        sent = []

        class Redactor:
            def redact(self, value):
                return RedactionResult(value, ())

        def transport(url, payload, timeout, headers):
            sent.append(payload)
            return self.reply()
        gateway = ProtocolHTTPGateway('http://gateway.invalid:4000', key='k' * 64, redactor=Redactor(), transport=transport)
        for step in ('model', 'model after tool'):
            gateway.complete('secure-financial-chat', json.dumps({'step': step, 'observations': []}), {})
        self.assertEqual([[m['role'] for m in p['messages']] for p in sent], [['system', 'user'], ['system', 'user']])
        self.assertNotIn('tools', sent[0])

    def test_shape_carries_no_text(self):
        from agent_platform import app
        response = self.reply(provider_specific_fields={'thought_signatures': ['b3BhcXVl']}, reasoning_content=self.SECRET)
        shape = app.response_shape(response)
        self.assertNotIn('Tenant', json.dumps(shape))
        self.assertNotIn('b3BhcXVl', json.dumps(shape))
        self.assertEqual(shape['finish_reason'], 'stop')
        self.assertEqual(shape['provider_specific_fields'], ['thought_signatures'])
        self.assertEqual(shape['kind'], 'tool')
        self.assertEqual(shape['usage']['reasoning_tokens'], 3)
        self.assertEqual(shape['decision_types'], {'kind': 'str:4', 'tool_id': 'str:15', 'arguments': 'dict:1'})
