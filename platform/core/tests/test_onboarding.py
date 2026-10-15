"""Agent onboarding: what a team may declare, what the platform refuses, and what every agent inherits."""
import copy
import json
import sys
import unittest

from agent_platform import onboarding
from agent_platform.onboarding import Rejected


FAKE_HASH = lambda passwords: {u: '$argon2id$v=19$fake' for u in passwords}


def template():
    """The Financial Agent's manifest with a small budget: the base for every rejection case."""
    manifest = copy.deepcopy(onboarding.load_all_unchecked()['financial'])
    manifest['model']['budget_usd_month'] = 0.5
    return manifest


def nodata():
    """An agent that declares no tools and no data (the smallest shape the platform accepts)."""
    manifest = template()
    manifest.update(agent='sample', tools=[], data='none')
    manifest['runtime'].update(image='app', port=8080)
    return manifest


def others(name='financial'):
    peer = template()  # a second agent at the maximum budget, so the shared $10 ceiling can be exercised
    peer.update(agent='peer')
    peer['model']['budget_usd_month'] = 5.0
    return [m for n, m in onboarding.load_all_unchecked().items() if n != name] + [peer]


class Rejections(unittest.TestCase):
    """Every way a manifest could ask for more than the platform allows is refused, with a reason."""

    def rejected(self, change, reason, name='financial', manifest=None):
        manifest = manifest or template()
        change(manifest)
        with self.assertRaisesRegex(Rejected, reason):
            onboarding.validate(manifest, name, others=others(name))

    def test_valid_manifests_are_accepted(self):
        manifests = onboarding.load_all()
        self.assertEqual(sorted(manifests), ['financial'])

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
        self.rejected(lambda m: m['model'].update(budget_usd_month=1.0), 'platform total would exceed')  # 4.5 + 5.0 + 1.0 > 10.0

    def test_redaction_cannot_be_turned_off(self):
        for value in ('optional', 'none', False):
            with self.subTest(value):
                self.rejected(lambda m: m.update(redaction=value), 'redaction: must be required')

    def test_tools_must_be_declared_read_only(self):
        tool = {'id': 'monthly_total', 'access': 'read', 'description': 'Total in a month.'}
        self.rejected(lambda m: m.update(tools=[dict(tool, access='write')]), 'not read-only')
        self.rejected(lambda m: m.update(tools=[dict(tool, id='delete_expenses')]), 'looks like a write')
        self.rejected(lambda m: m.update(tools=[dict(tool, id='transfer_money')]), 'looks like a write')
        self.rejected(lambda m: m.update(tools=[dict(tool, sql='DELETE FROM x')]), 'tools\\[\\]: not allowed: sql')
        self.rejected(lambda m: m.update(tools=[tool, tool]), 'distinct')
        self.rejected(lambda m: m.update(tools=[dict(tool, id='t' + 'x' * i) for i in range(6)]), 'up to 5')

    def test_data_is_read_only_under_row_level_security(self):
        data = {'database': 'finance', 'agent_access': 'read', 'user_entry': 'own-rows', 'row_level_security': 'required'}
        self.rejected(lambda m: m.update(data=dict(data, agent_access='write')), 'agent_access: read only')
        self.rejected(lambda m: m.update(data=dict(data, database='postgres')), 'platform database')
        self.rejected(lambda m: m.update(data=dict(data, row_level_security='off')), 'row_level_security: required')
        self.rejected(lambda m: m.update(data=dict(data, user_entry='any-rows')), 'user_entry')
        self.rejected(lambda m: m.update(data=dict(data, bypass_rls=True)), 'data: not allowed: bypass_rls')
        self.rejected(lambda m: m.update(data=dict(data, role='postgres')), 'data: not allowed: role')

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

    def test_remediation_rights_are_not_granted(self):
        self.rejected(lambda m: m.update(operations='restart'), 'only observe')
        self.rejected(lambda m: m.update(operations={'remediation': 'restart'}), 'only observe')
        manifest = template()
        manifest['operations'] = 'observe'
        onboarding.validate(manifest, 'financial', others=others())

    def test_ops_agent_gets_read_only_observe_rights(self):
        docs = onboarding.render_ops_observe(onboarding.load_all())
        roles = [d for d in docs if d['kind'] == 'Role']
        self.assertEqual(sorted(r['metadata']['namespace'] for r in roles), ['agent-financial'])
        for role in roles:
            self.assertTrue(all(set(rule['verbs']) <= {'get', 'list'} for rule in role['rules']))
            self.assertNotIn('secrets', json.dumps(role))
        self.assertEqual(docs[0]['data'], {'agent-financial.agent.observe': 'read-only'})

    def test_names_and_placement(self):
        for name in ('platform', 'ops', 'kube-system', 'gateway', 'A', 'x'):
            with self.subTest(name), self.assertRaises(Rejected):
                onboarding.load(name)
        self.rejected(lambda m: m.update(agent='other'), 'match its directory')
        self.rejected(lambda m: m.update(placement='front-door'), 'placement: namespace')
        self.rejected(lambda m: m.pop('runtime'), 'runtime: required')


class Inheritance(unittest.TestCase):
    """What the platform generates for an onboarded agent (the team never writes these)."""

    def setUp(self):
        self.docs = {(d['kind'], d['metadata']['name']): d for d in onboarding.render_agent(nodata())}

    def test_isolated_namespace_with_no_exposure(self):
        ns = self.docs[('Namespace', 'agent-sample')]
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
        self.assertEqual(sorted(p['metadata']['name'] for p in access),
                         ['agent-financial-to-gateway', 'agent-financial-to-postgres', 'agent-financial-to-redactor'])

    def test_database_path_only_when_declared(self):
        ports = lambda manifest: sorted(e['ports'][0]['port'] for e in onboarding.egress(manifest))
        self.assertEqual((ports(nodata()), ports(onboarding.load_all()['financial'])), ([4000, 4003], [4000, 4003, 5432]))

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
        self.assertEqual(limits, {'app-infrastructure': 2.5, 'ops-explain': 2.0, 'app-financial': 0.0,  # retired, refused at the gateway
                                  'agent-financial': 5.0})
        self.assertLessEqual(round(sum(limits.values()), 2), 10.0)


class FinancialTenantOne(unittest.TestCase):
    """The Financial Agent's manifest is bound to its code: same read-only tools, its own image, its own data rules."""

    def test_manifest_matches_the_agent_code(self):
        sys.path.insert(0, str(onboarding.REPO / 'platform/agents/financial'))
        from finance_agent.tools import READ_ONLY, TOOLS
        financial = onboarding.load_all()['financial']
        self.assertEqual({t['id'] for t in financial['tools']}, set(TOOLS))
        self.assertEqual(set(TOOLS), set(READ_ONLY))
        self.assertTrue(all(t['access'] == 'read' for t in financial['tools']))
        self.assertEqual((financial['runtime']['image'], financial['data']['database']), ('agent-financial', 'finance'))
        self.assertIn('FORCE ROW LEVEL SECURITY', (onboarding.REPO / 'platform/core/database/finance.sql').read_text())

    def test_secrets_give_it_only_its_own_keys_and_hashed_users(self):
        from agent_platform import platform_secrets
        passwords = {}
        docs = {(d['metadata']['namespace'], d['metadata']['name']): d
                for d in platform_secrets.generate('correct horse battery', hasher=FAKE_HASH, users_out=passwords)}
        decode = lambda d, k: json.loads(__import__('base64').b64decode(d['data'][k]))
        boot = decode(docs[('platform', 'bootstrap')], 'bootstrap.json')
        agent = decode(docs[('agent-financial', 'agent')], 'agent.json')
        self.assertEqual(set(agent), {'gateway_key', 'redactor_key', 'web_db_url', 'agent_db_url', 'session_key'})
        self.assertIn('finance_web:' + boot['finance']['web_password'], agent['web_db_url'])
        self.assertIn('finance_agent:' + boot['finance']['agent_password'], agent['agent_db_url'])
        self.assertEqual(sorted(passwords), ['lama', 'omar', 'sara'])
        self.assertTrue(all(u['password_hash'].startswith('$argon2id$') for u in boot['finance']['users']))
        for password in passwords.values():  # plaintext passwords never enter the cluster
            self.assertNotIn(password, json.dumps([d['data'] for d in docs.values()]))
            self.assertNotIn(password, json.dumps(boot))


if __name__ == '__main__':
    unittest.main()
