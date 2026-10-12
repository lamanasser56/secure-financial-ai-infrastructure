"""Agent onboarding: what a team may declare, what the platform refuses, and what every agent inherits."""
import copy
import io
import json
import unittest

from agent_platform import onboarding
from agent_platform.onboarding import Rejected


def hello():
    return copy.deepcopy(onboarding.load_all_unchecked()['hello'])


def others(name='hello'):
    return [m for n, m in onboarding.load_all_unchecked().items() if n != name]


class Rejections(unittest.TestCase):
    """Every way a manifest could ask for more than the platform allows is refused, with a reason."""

    def rejected(self, change, reason, name='hello', manifest=None):
        manifest = manifest or hello()
        change(manifest)
        with self.assertRaisesRegex(Rejected, reason):
            onboarding.validate(manifest, name, others=others(name))

    def test_valid_manifests_are_accepted(self):
        manifests = onboarding.load_all()
        self.assertEqual(sorted(manifests), ['financial', 'hello'])

    def test_no_extra_powers_can_be_requested(self):
        for field, value in (('egress', ['0.0.0.0/0']), ('privileged', True), ('hostPath', '/'), ('serviceType', 'LoadBalancer'),
                             ('rbac', [{'resources': ['secrets'], 'verbs': ['get']}]), ('namespace', 'platform'),
                             ('provider_api_key', 'sk-x'), ('approval', 'auto')):
            with self.subTest(field):
                self.rejected(lambda m: m.update({field: value}), 'manifest: not allowed: ' + field)

    def test_model_access_is_only_a_budget(self):
        for field, value in (('provider', 'openai'), ('name', 'gpt-x'), ('api_key', 'sk-x'), ('endpoint', 'https://api.example.com')):
            with self.subTest(field):
                self.rejected(lambda m: m['model'].update({field: value}), 'model: not allowed: ' + field)

    def test_budget_bounds_and_platform_total(self):
        self.rejected(lambda m: m['model'].update(budget_usd_month=0.0), 'budget_usd_month')
        self.rejected(lambda m: m['model'].update(budget_usd_month=-1.0), 'budget_usd_month')
        self.rejected(lambda m: m['model'].update(budget_usd_month=1), 'budget_usd_month')  # must be dollars, e.g. 1.0
        self.rejected(lambda m: m['model'].update(budget_usd_month=1.0), 'platform total would exceed')  # 10.50 > 10.00

    def test_redaction_cannot_be_turned_off(self):
        for value in ('optional', 'none', False):
            with self.subTest(value):
                self.rejected(lambda m: m.update(redaction=value), 'redaction: must be required')

    def test_tools_must_be_registered_enabled_and_read_only(self):
        self.rejected(lambda m: m.update(tools=['delete_all_expenses']), 'tool not registered')
        self.rejected(lambda m: m.update(tools=['expense_summary', 'expense_summary']), 'distinct')
        registry = onboarding.tools_registry()
        original = onboarding.tools_registry
        try:
            for change, reason in ((dict(operation_type='write'), 'not read-only'), (dict(risk_classification='high_risk_write'), 'not read-only'),
                                   (dict(enabled=False), 'disabled'), (dict(approval={'required': True}), 'needs approval')):
                tampered = {k: dict(v, **change) if k == 'expense_summary' else v for k, v in registry.items()}
                onboarding.tools_registry = lambda tampered=tampered: tampered
                with self.subTest(change):
                    self.rejected(lambda m: m.update(tools=['expense_summary']), reason)
        finally:
            onboarding.tools_registry = original

    def test_data_is_read_only_under_row_level_security(self):
        data = {'role': 'portfolio_app', 'access': 'read', 'row_level_security': 'required'}
        self.rejected(lambda m: m.update(data=dict(data, access='write')), 'read only')
        self.rejected(lambda m: m.update(data=dict(data, role='postgres')), 'existing platform role')
        self.rejected(lambda m: m.update(data=dict(data, row_level_security='off')), 'row_level_security: required')
        self.rejected(lambda m: m.update(data=dict(data, bypass_rls=True)), 'data: not allowed: bypass_rls')

    def test_runtime_is_bounded_and_signed(self):
        for change, reason in ((lambda r: r.update(image='nginx:latest'), 'signed and pinned'),
                               (lambda r: r.update(image='gateway'), 'signed and pinned'),  # a platform component image
                               (lambda r: r.update(port=80), 'no privileged ports'),
                               (lambda r: r.update(replicas=5), 'replicas'),
                               (lambda r: r['resources'].update(cpu='4000m'), 'cpu'),
                               (lambda r: r['resources'].update(memory='8Gi'), 'memory'),
                               (lambda r: r.update(securityContext={'privileged': True}), 'runtime: not allowed: securityContext'),
                               (lambda r: r.update(hostNetwork=True), 'runtime: not allowed: hostNetwork')):
            with self.subTest(reason):
                self.rejected(lambda m: change(m['runtime']), reason)

    def test_names_and_placement(self):
        for name in ('platform', 'ops', 'kube-system', 'gateway', 'A', 'x'):
            with self.subTest(name), self.assertRaises(Rejected):
                onboarding.load(name)
        self.rejected(lambda m: m.update(agent='other'), 'match its directory')
        self.rejected(lambda m: m.update(placement='front-door'), 'reserved for the legacy Financial Agent')
        self.rejected(lambda m: m.pop('runtime'), 'runtime: required')


class Inheritance(unittest.TestCase):
    """What the platform generates for an onboarded agent (the team never writes these)."""

    def setUp(self):
        self.docs = {(d['kind'], d['metadata']['name']): d for d in onboarding.render_agent(hello())}

    def test_isolated_namespace_with_no_exposure(self):
        ns = self.docs[('Namespace', 'agent-hello')]
        self.assertEqual(ns['metadata']['labels']['pod-security.kubernetes.io/enforce'], 'restricted')
        hard = self.docs[('ResourceQuota', 'bounds')]['spec']['hard']
        self.assertEqual((hard['services.loadbalancers'], hard['services.nodeports']), ('0', '0'))
        self.assertEqual(self.docs[('Service', 'agent')]['spec']['type'], 'ClusterIP')

    def test_network_reaches_only_the_redactor_and_the_gateway(self):
        self.assertEqual(self.docs[('NetworkPolicy', 'default-deny')]['spec'], {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress']})
        egress = self.docs[('NetworkPolicy', 'agent')]['spec']['egress']
        targets = {(e['to'][0]['podSelector']['matchLabels']['app.kubernetes.io/name'], e['ports'][0]['port']) for e in egress}
        self.assertEqual(targets, {('gateway', 4000), ('redactor', 4003)})
        access = onboarding.render_platform_access(onboarding.load_all())
        self.assertEqual(sorted(p['metadata']['name'] for p in access), ['agent-hello-to-gateway', 'agent-hello-to-redactor'])

    def test_hardened_pod_without_api_token(self):
        pod = self.docs[('Deployment', 'agent')]['spec']['template']['spec']
        self.assertIs(pod['automountServiceAccountToken'], False)
        self.assertEqual(pod['securityContext']['fsGroup'], 65532)  # live 2026-10-12: without it the 0400 key file was unreadable
        self.assertIs(self.docs[('ServiceAccount', 'agent')]['automountServiceAccountToken'], False)
        container = pod['containers'][0]
        self.assertEqual(container['securityContext']['capabilities'], {'drop': ['ALL']})
        self.assertIs(container['securityContext']['readOnlyRootFilesystem'], True)
        self.assertEqual(container['image'], 'agent-platform/app')  # pinned to the signed digest by the cloud renderer

    def test_budgets_sum_to_the_platform_total(self):
        limits = onboarding.budgets(onboarding.load_all())
        self.assertEqual(limits, {'app-infrastructure': 2.5, 'ops-explain': 2.0, 'app-financial': 5.0, 'agent-hello': 0.5})
        self.assertEqual(round(sum(limits.values()), 2), 10.0)


class FinancialTenantOne(unittest.TestCase):
    """The Financial Agent's manifest declares exactly what the platform gives it today (no drift)."""

    def test_manifest_matches_the_running_configuration(self):
        from runtime.agents.controls import PROFILES
        from agent_platform import platform_secrets
        financial = onboarding.load_all()['financial']
        self.assertEqual(set(financial['tools']), set(PROFILES['financial']))
        self.assertEqual(onboarding.key_alias(financial), 'app-financial')
        docs = {(d['metadata']['namespace'], d['metadata']['name']): d for d in platform_secrets.generate('correct horse battery')}
        boot = json.loads(__import__('base64').b64decode(docs[('platform', 'bootstrap')]['data']['bootstrap.json']))
        self.assertEqual({k['alias']: k['max_budget'] for k in boot['virtual_keys']}['app-financial'], financial['model']['budget_usd_month'])
        tenant = (onboarding.REPO / 'platform/core/database/tenant.sql').read_text()
        self.assertIn('FORCE ROW LEVEL SECURITY', tenant.upper())


class HelloAgent(unittest.TestCase):
    """The hello agent fails closed: no model request without a redaction first; incomplete replies are refused."""

    class Redactor:
        def __init__(self, fail=False):
            self.fail, self.seen = fail, []

        def redact(self, value):
            from runtime.phase3.trusted_runtime import ControlFailure, RedactionResult
            if self.fail:
                raise ControlFailure('presidio_anonymizer', 'unavailable')
            self.seen.append(value)
            masked = value.replace('lama@example.com', '[EMAIL_ADDRESS]')
            return RedactionResult(masked, ('EMAIL_ADDRESS',) if masked != value else ())

    def agent(self, redactor, finish='stop', content='Hello there!'):
        from agent_platform.programs import hello_agent
        sent = []

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(request, timeout):
            sent.append(json.loads(request.data))
            return Response(json.dumps({'choices': [{'finish_reason': finish, 'message': {'content': content}}]}).encode())
        return hello_agent.Agent({'gateway_key': 'sk-x', 'redactor_key': 'k' * 64}, redactor=redactor, opener=opener), sent

    def test_name_is_redacted_before_the_model(self):
        agent, sent = self.agent(self.Redactor())
        status, body = agent.hello('lama@example.com')
        self.assertEqual((status, body['masked']), (200, ['EMAIL_ADDRESS']))
        self.assertNotIn('lama@example.com', json.dumps(sent))
        self.assertEqual(sent[0]['model'], 'secure-financial-chat')

    def test_redaction_failure_sends_nothing(self):
        agent, sent = self.agent(self.Redactor(fail=True))
        self.assertEqual(agent.hello('Lama')[0], 503)
        self.assertEqual(sent, [])

    def test_incomplete_reply_and_bad_input_are_refused(self):
        agent, _ = self.agent(self.Redactor(), finish='length')
        self.assertEqual(agent.hello('Lama')[0], 503)
        agent, sent = self.agent(self.Redactor())
        for name in ('', ' ', 'x' * 61, 5):
            self.assertEqual(agent.hello(name)[0], 400)
        self.assertEqual(sent, [])


if __name__ == '__main__':
    unittest.main()
