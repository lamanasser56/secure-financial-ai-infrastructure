"""Console data API (offline): manifest facts, live facts from a fake ops agent, honest "declared" vs "verified", proof is
live or null, no secrets and no project ID in any response, unknown names are 404."""
import json
from pathlib import Path
import re
import threading
import unittest
import urllib.error
import urllib.request

import yaml

from agent_platform import audit, console
from agent_platform.ops import activity, diagnose, posture
from agent_platform.ops.agent import Agent
from runtime.agents.web import DemoServer

REPO = Path(__file__).resolve().parents[3]
KUBE = REPO / 'platform/core/kubernetes'
NOW = 1_800_000_000.0
DIGEST = 'sha256:' + 'c' * 64
# What a leak would look like: a registry path with a project, a service account, the unrendered placeholder, a bearer key.
LEAKS = re.compile(r'pkg\.dev|gserviceaccount|PROJECT_ID|Bearer|api_key|master_key|private_key|BEGIN [A-Z ]*KEY|(?<!sha256:)\b[0-9a-f]{64}\b')


def netpols():
    """The real rendered NetworkPolicies per namespace, as the Kubernetes API would list them."""
    found = {}
    for path in [KUBE / 'policies/network.yaml', *sorted((KUBE / 'agents').glob('*.yaml'))]:
        for doc in yaml.safe_load_all(path.read_text()):
            if doc and doc.get('kind') == 'NetworkPolicy':
                found.setdefault(doc['metadata']['namespace'], []).append(doc)
    return found


class KubeStub:
    """Read-only Kubernetes stub: real NetworkPolicies, no pods; `unreadable` namespaces answer 403 like missing RBAC."""

    def __init__(self, unreadable=(), forbidden_kinds=()):
        self.policies, self.unreadable, self.forbidden_kinds = netpols(), set(unreadable), set(forbidden_kinds)
        self.rbac = [d for path in [KUBE / 'policies/ops-agent-rbac.yaml', KUBE / 'agents/ops-observe.yaml']
                     for d in yaml.safe_load_all(path.read_text()) if d and d['kind'] in ('Role', 'RoleBinding')]

    def list(self, kind, namespace, selector=None):
        from agent_platform.k8s import KubeError
        if namespace in self.unreadable or kind in self.forbidden_kinds:
            raise KubeError(403, 'Forbidden')
        if kind in ('roles', 'rolebindings'):
            return [d for d in self.rbac if d['kind'] == {'roles': 'Role', 'rolebindings': 'RoleBinding'}[kind]
                    and d['metadata']['namespace'] == namespace]
        return self.policies.get(namespace, []) if kind == 'networkpolicies' else []


def checked_posture(client, namespaces):
    workloads = {ns: [] for ns in namespaces}
    for path in (KUBE / 'agents').glob('*.yaml'):
        for doc in yaml.safe_load_all(path.read_text()):
            if doc and doc.get('kind') == 'Deployment' and doc['metadata']['namespace'] in workloads:
                workloads[doc['metadata']['namespace']].append(doc['metadata']['name'])
    return posture.check(client, namespaces, workloads)


def finding(namespace, name, **facts):
    base = {'pods_total': 1, 'pods_ready': 1, 'restarts': 0, 'image_digests': [DIGEST], 'observed_at': NOW - 5}
    return {'deployment': name, 'namespace': namespace, 'finding': 'HEALTHY', 'desired_replicas': 1, 'available_replicas': 1,
            'facts': dict(base, **facts)}


def ops_answers(**override):
    answers = {
        '/v1/snapshot': {'timeline': [
            {'stage': 'observed', 'target': 'apps.app', 'at': NOW - 90},
            {'stage': 'denied', 'target': 'apps.fault-demo', 'at': NOW - 60, 'code': 'APPROVAL_DENIED', 'request_id': 'r1'},
            {'stage': 'approved', 'target': 'apps.fault-demo', 'at': NOW - 30, 'request_id': 'r2', 'approver': 'owner'}],
            'findings': {'agent-financial.agent': finding('agent-financial', 'agent'),
                         'agent-platform-guide.agent': finding('agent-platform-guide', 'agent'),
                         'platform.redactor': finding('platform', 'redactor'),
                         'platform.gateway': finding('platform', 'gateway')}},
        '/v1/posture': checked_posture(KubeStub(unreadable=('agent-financial', 'agent-platform-guide')), ['apps', 'platform',
                                                                                                         'agent-financial', 'agent-platform-guide']),
        '/v1/activity': {'available': True, 'events': [
            {'kind': 'masked', 'at': NOW - 10, 'source': 'redactor', 'caller': 'agent-financial', 'categories': ['EMAIL_ADDRESS'], 'reason': None}]}}
    answers.update(override)
    return answers


def make(answers=None, *, audit_lines=()):
    answers = ops_answers() if answers is None else answers

    def ops(path):
        if path not in answers or answers[path] is None:
            raise OSError('unreachable')
        return answers[path]
    return console.Console(ops, clock=lambda: NOW, recent_audit=lambda: list(audit_lines))


def walk(value):
    return json.dumps(value, sort_keys=True)


class OpsFacts(unittest.TestCase):
    def test_running_digest_only_never_the_registry_path(self):
        pod = {'status': {'phase': 'Running', 'containerStatuses': [
            {'ready': True, 'restartCount': 2, 'imageID': 'us-east1-docker.pkg.dev/some-project/repo/agent@' + DIGEST}]}}
        facts = diagnose.live_facts([pod, {'status': {'phase': 'Pending'}}])
        self.assertEqual(facts, {'pods_total': 2, 'pods_ready': 1, 'restarts': 2, 'image_digests': [DIGEST]})
        self.assertNotIn('some-project', json.dumps(facts))

    def test_scan_attaches_facts_without_changing_the_evidence_digest(self):
        from fixtures import FakeClient, REGISTRY, deployment, pod
        from agent_platform.ops.approval import Verifier
        client = FakeClient(deployment(tmpl=None), [pod()])
        agent = Agent(client, {'apps.fault-demo': REGISTRY['apps.fault-demo']}, Verifier.__new__(Verifier), clock=lambda: NOW)
        agent.scan()
        found = agent.findings['apps.fault-demo']
        self.assertEqual((found['facts']['pods_ready'], found['facts']['observed_at']), (1, NOW))
        self.assertEqual(found['evidence_digest'], diagnose.diagnose(client.deployment, [pod()], [])['evidence_digest'])

    def test_posture_reports_policy_shapes_and_unreadable_namespaces(self):
        result = checked_posture(KubeStub(unreadable=('agent-financial',)), ['apps', 'agent-financial'])
        self.assertIn('apps', result['network'])
        self.assertEqual(result['unreadable'], ['agent-financial'])
        self.assertNotIn('agent-financial', result['network'])
        default_deny = next(p for p in result['network']['apps'] if p['name'] == 'default-deny')
        self.assertEqual((default_deny['pods'], default_deny['types'], default_deny['egress']), ('all', ['Egress', 'Ingress'], []))

    def test_posture_reads_network_policies_even_when_other_lists_are_forbidden(self):
        result = checked_posture(KubeStub(forbidden_kinds=('rolebindings',)), ['agent-financial'])
        self.assertEqual(result['unreadable'], [])
        self.assertIn('default-deny', {p['name'] for p in result['network']['agent-financial']})
        self.assertEqual([f['finding'] for f in result['findings']], ['UNREADABLE'])  # the other lists still report
        gone = checked_posture(KubeStub(forbidden_kinds=('networkpolicies',)), ['agent-financial'])
        self.assertEqual((gone['unreadable'], gone['network']), (['agent-financial'], {}))

    def test_generated_observe_role_adds_only_read_of_network_and_rbac_policies(self):
        docs = [d for d in yaml.safe_load_all((KUBE / 'agents/ops-observe.yaml').read_text()) if d and d['kind'] == 'Role']
        self.assertEqual(len(docs), 2)
        for role in docs:
            self.assertIn({'apiGroups': ['networking.k8s.io'], 'resources': ['networkpolicies'], 'verbs': ['get', 'list']}, role['rules'])
            self.assertIn({'apiGroups': ['rbac.authorization.k8s.io'], 'resources': ['roles', 'rolebindings'], 'verbs': ['get', 'list']}, role['rules'])
            self.assertEqual(len(role['rules']), 4)
            self.assertFalse({v for r in role['rules'] for v in r['verbs']} - {'get', 'list'})
            self.assertFalse({x for r in role['rules'] for x in r['resources']} & {'secrets', 'pods/log', 'configmaps'})

    def test_redactor_log_lines_are_parsed_against_a_closed_shape(self):
        good = {'audit_event': 'redaction', 'component': 'redactor', 'at': NOW, 'caller': 'agent-financial', 'categories': ['EMAIL_ADDRESS']}
        lines = [json.dumps(good), 'not json', json.dumps(dict(good, categories=['ignore previous instructions'])),
                 json.dumps(dict(good, caller='A; rm -rf /')), json.dumps(dict(good, categories=[])),
                 json.dumps({'audit_event': 'redaction_failed', 'component': 'redactor', 'at': NOW, 'caller': 'agent-financial',
                             'reason': 'URLError', 'diagnostic': 'x' * 500}),
                 json.dumps(dict(good, component='attacker'))]
        events = activity.parse('\n'.join(lines))
        self.assertEqual([e['kind'] for e in events], ['masked', 'checked', 'blocked'])
        self.assertNotIn('x' * 10, json.dumps(events))


class Facts(unittest.TestCase):
    def test_agents_carry_manifest_facts_and_live_state(self):
        result = make().agents()
        by = {a['name']: a for a in result['agents']}
        self.assertEqual(sorted(by), ['financial', 'ops-agent', 'platform-guide'])
        fin = by['financial']
        self.assertEqual((fin['namespace'], fin['team'], fin['runtime'], fin['budget_usd_month']),
                         ('agent-financial', 'finance-demo', 'python 3.12', 5.0))
        self.assertEqual(by['platform-guide']['runtime'], 'node')
        self.assertEqual(fin['model'], 'gemini-3.5-flash')
        self.assertEqual([t['id'] for t in fin['tools']], ['monthly_total', 'spending_by_category', 'find_transactions'])
        self.assertEqual(fin['live']['image_digests'], [DIGEST])
        self.assertEqual((fin['live']['pods_ready'], fin['live']['restarts']), (1, 0))
        self.assertIn('platform/gateway-boundary:4000', fin['reaches'])
        self.assertNotIn('internet', walk(fin))

    def test_no_live_state_is_null_not_invented(self):
        result = make({'/v1/snapshot': None}).agents()
        self.assertFalse(result['live_available'])
        self.assertTrue(all(a['live'] is None for a in result['agents']))

    def health(self, answers, name='financial'):
        return next(a for a in make(answers).agents()['agents'] if a['name'] == name)['health']

    def test_live_health_is_running_not_ready_or_absent(self):
        self.assertEqual(self.health(None)['state'], 'running')
        notready = ops_answers()
        notready['/v1/snapshot']['findings']['agent-financial.agent']['facts'].update(pods_ready=0)
        self.assertEqual(self.health(notready)['state'], 'not_ready')
        gone = ops_answers()
        del gone['/v1/snapshot']['findings']['agent-financial.agent']
        self.assertEqual(self.health(gone)['state'], 'absent')
        empty = ops_answers()
        empty['/v1/snapshot']['findings']['agent-financial.agent']['facts'].update(pods_ready=0, pods_total=0)
        self.assertEqual(self.health(empty)['state'], 'absent')

    def test_health_is_unknown_not_absent_when_the_source_cannot_say(self):
        self.assertIsNone(self.health({}))
        stale = ops_answers()
        stale['/v1/snapshot']['findings']['agent-financial.agent']['facts']['observed_at'] = NOW - 3600
        self.assertIsNone(self.health(stale))

    def test_stale_live_state_is_not_live(self):
        stale = ops_answers()
        for f in stale['/v1/snapshot']['findings'].values():
            f['facts']['observed_at'] = NOW - 3600
        self.assertTrue(all(a['live'] is None for a in make(stale).agents()['agents'] if a['kind'] == 'agent'))

    def test_topology_from_manifests(self):
        topology = make().topology()
        ids = {n['id'] for n in topology['nodes']}
        self.assertTrue({'agent-financial', 'agent-platform-guide', 'gateway', 'redactor', 'audit', 'internet'} <= ids)
        edges = {(e['from'], e['to']) for e in topology['edges']}
        self.assertTrue({('agent-financial', 'gateway-boundary'), ('agent-financial', 'redactor'), ('agent-financial', 'financial-frontdoor'),
                         ('agent-platform-guide', 'gateway-boundary'), ('agent-platform-guide', 'redactor')} <= edges)
        self.assertNotIn(('agent-platform-guide', 'postgres'), edges)  # declared data: none
        self.assertFalse([e for e in edges if e[1] == 'internet'])
        denied = {(d['from'], d['to']) for d in topology['denied']}
        self.assertIn(('agent-platform-guide', 'agent-financial'), denied)
        self.assertIn(('agent-financial', 'internet'), denied)
        hosts = {n.get('host') for n in topology['nodes']}
        self.assertTrue(all(h is None or h.endswith('.googleapis.com') for h in hosts))
        self.assertEqual(topology['live'], False)


class OpsTenant(unittest.TestCase):
    """The Security & Operations Agent from its real config (ops namespace), with honest guarantees."""

    def ops(self, answers=None):
        return next(a for a in make(answers).agents()['agents'] if a['name'] == 'ops-agent')

    def test_facts_come_from_its_real_config(self):
        o = self.ops()
        self.assertEqual((o['kind'], o['display'], o['namespace'], o['runtime'], o['port'], o['budget_usd_month']),
                         ('platform', 'Security & Ops', 'ops', 'python 3.12', 8090, 2.0))
        self.assertEqual({t['target'] for t in o['targets']}, {'platform.gateway', 'platform.redactor', 'apps.app', 'apps.fault-demo'})
        self.assertEqual([t['id'] for t in o['tools']], ['observe', 'restart', 'scale'])
        self.assertEqual([t['access'] for t in o['tools']], ['read', 'approval', 'approval'])
        self.assertIn('platform/gateway-boundary:4000', o['reaches'])
        self.assertIn('kubernetes API (private control-plane range)', o['reaches'])
        self.assertEqual(o['health']['state'], 'running')
        self.assertEqual(o['live']['image_digests'], [])  # it does not observe its own pod: no digest is claimed

    def test_unreachable_ops_agent_is_unknown_not_absent(self):
        o = self.ops({})
        self.assertIsNone(o['live'])
        self.assertIsNone(o['health'])

    def test_guarantees_are_honest(self):
        result = make().onboarding('ops-agent')
        states = {g['id']: g['state'] for g in result['guarantees']}
        self.assertEqual([g['id'] for g in result['guarantees']], list(console.OPS_GUARANTEES))
        self.assertEqual(states, {'namespace': 'verified', 'network': 'declared', 'model_key': 'declared', 'budget': 'declared',
                                  'redaction': 'declared', 'approval': 'declared', 'image': 'declared'})
        self.assertEqual((result['counts'], result['total']), ({'verified': 1, 'declared': 6, 'failing': 0}, 7))
        answers = ops_answers()
        answers['/v1/activity']['events'].append({'kind': 'masked', 'at': NOW - 5, 'source': 'redactor', 'caller': 'ops', 'categories': ['EMAIL_ADDRESS']})
        self.assertEqual(next(g for g in make(answers).onboarding('ops-agent')['guarantees'] if g['id'] == 'redaction')['state'], 'verified')
        self.assertEqual(make({}).onboarding('ops-agent')['counts'], {'verified': 0, 'declared': 7, 'failing': 0})

    def test_topology_places_it_and_denies_what_its_policies_deny(self):
        t = make().topology()
        self.assertIn('ops-agent', {n['id'] for n in t['nodes']})
        edges = {(e['from'], e['to']) for e in t['edges']}
        self.assertTrue({('ops-agent', 'gateway-boundary'), ('ops-agent', 'redactor')} <= edges)
        denied = {(d['from'], d['to']) for d in t['denied']}
        for pair in (('agent-financial', 'ops-agent'), ('ops-agent', 'agent-financial'), ('ops-agent', 'internet')):
            self.assertIn(pair, denied)


class AttackNotes(unittest.TestCase):
    def test_the_latest_note_is_attached_verbatim_to_its_failed_case(self):
        # The run-3 note against a copy of the results in which its case failed, as it did in run 3.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            results = json.loads((REPO / 'docs/evidence/attack-suite.json').read_text())
            for r in results['results']:
                if r['case'] == 'financial_redaction_down_no_model_call':
                    r['result'] = 'FAIL'
            (Path(tmp) / 'attack-suite.json').write_text(json.dumps(results))
            (Path(tmp) / 'attack-suite-run-3-note.json').write_text((REPO / 'docs/evidence/attack-suite-run-3-note.json').read_text())
            c = make()
            c.evidence_dir = Path(tmp)
            noted = [r for r in c.attacks()['results'] if 'note' in r]
        self.assertEqual([r['case'] for r in noted], ['financial_redaction_down_no_model_call'])
        evidence = json.loads((REPO / 'docs/evidence/attack-suite-run-3-note.json').read_text())
        self.assertEqual(noted[0]['note'], {'conclusion': evidence['conclusion'], 'file': 'docs/evidence/attack-suite-run-3-note.json'})
        self.assertEqual(noted[0]['result'], 'FAIL')  # not relabelled

    def test_the_recorded_run_5_has_no_failed_case_and_no_note_attached(self):
        data = make().attacks()
        self.assertEqual((data['source'], data['stopped'], data['total']), ('recorded', 18, 18))  # 19 suite cases minus the setup step
        self.assertFalse([r for r in data['results'] if 'note' in r])
        note = json.loads((REPO / 'docs/evidence/attack-suite-run-5-note.json').read_text())
        self.assertNotIn('case', note)  # the run-5 note is about passes that did not exercise their control, not a failure
        self.assertEqual(note['run_5_result'], '19/19')

    def test_without_a_note_file_nothing_is_attached(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(REPO / 'docs/evidence/attack-suite.json', tmp)
            c = make()
            c.evidence_dir = Path(tmp)
            self.assertFalse([r for r in c.attacks()['results'] if 'note' in r])


class Onboarding(unittest.TestCase):
    def test_eight_guarantees_verified_or_declared_with_sources(self):
        result = make().onboarding('financial')
        self.assertEqual([g['id'] for g in result['guarantees']], list(console.GUARANTEES))
        states = {g['id']: g['state'] for g in result['guarantees']}
        self.assertEqual(states, {'namespace': 'verified', 'network': 'declared', 'model_key': 'declared', 'budget': 'declared',
                                  'redaction': 'verified', 'tools': 'declared', 'image': 'verified', 'ops': 'verified'})
        self.assertEqual(result['counts'], {'verified': 4, 'declared': 4, 'failing': 0})
        self.assertEqual((result['verified'], result['total']), (4, 8))
        image = next(g for g in result['guarantees'] if g['id'] == 'image')
        self.assertEqual(image['basis'], 'inference')
        self.assertIn('inferred', image['detail'])
        self.assertTrue(all(g['source'] for g in result['guarantees']))
        self.assertTrue(all(g['basis'] == 'manifest' for g in result['guarantees'] if g['state'] == 'declared'))

    def test_without_live_data_nothing_is_verified(self):
        result = make({}).onboarding('platform-guide')
        self.assertEqual(result['counts'], {'verified': 0, 'declared': 8, 'failing': 0})
        self.assertEqual({g['state'] for g in result['guarantees']}, {'declared'})

    def test_network_is_verified_only_when_the_live_policy_list_shows_default_deny(self):
        answers = ops_answers()
        answers['/v1/posture'] = checked_posture(KubeStub(), ['agent-financial'])
        network = next(g for g in make(answers).onboarding('financial')['guarantees'] if g['id'] == 'network')
        self.assertEqual((network['state'], network['source']), ('verified', 'ops-agent /v1/posture'))

    def test_redaction_is_verified_only_by_a_recent_event_for_that_agents_own_key(self):
        state = lambda c, name: next(g for g in c.onboarding(name)['guarantees'] if g['id'] == 'redaction')
        self.assertEqual(state(make(), 'financial')['state'], 'verified')
        self.assertEqual(state(make(), 'financial')['basis'], 'observed')
        self.assertEqual(state(make(), 'platform-guide')['state'], 'declared')  # the only event is another agent's
        old = ops_answers()
        old['/v1/activity']['events'][0]['at'] = NOW - 7200
        self.assertEqual(state(make(old), 'financial')['state'], 'declared')
        old['/v1/activity']['events'][0].update(at=NOW - 5, caller='app')
        self.assertEqual(state(make(old), 'financial')['state'], 'declared')
        old['/v1/activity'] = None
        self.assertEqual(state(make(old), 'financial')['state'], 'declared')

    def test_failing_means_a_live_check_ran_and_contradicts_the_manifest(self):
        answers = ops_answers()
        weak = checked_posture(KubeStub(), ['agent-financial'])
        weak['network']['agent-financial'] = [p for p in weak['network']['agent-financial'] if p['name'] != 'default-deny']
        answers['/v1/posture'] = weak
        result = make(answers).onboarding('financial')
        network = next(g for g in result['guarantees'] if g['id'] == 'network')
        self.assertEqual((network['state'], network['source']), ('failing', 'ops-agent /v1/posture'))
        self.assertEqual(result['counts']['failing'], 1)
        notready = ops_answers()
        notready['/v1/snapshot']['findings']['agent-financial.agent']['facts'].update(pods_ready=0)
        notready['/v1/snapshot']['findings']['agent-financial.agent']['finding'] = 'READINESS_FAILING'
        result = make(notready).onboarding('financial')
        image = next(g for g in result['guarantees'] if g['id'] == 'image')
        self.assertEqual(image['state'], 'declared')  # a not-ready pod says nothing about the signature
        self.assertEqual(result['counts']['failing'], 0)
        # a check that could not run is never "failing"
        self.assertEqual(make({}).onboarding('financial')['counts']['failing'], 0)

    def test_unknown_agent(self):
        self.assertIsNone(make().onboarding('nope'))
        self.assertIsNone(make().onboarding('../../etc/passwd'))


class Activity(unittest.TestCase):
    def test_latest_events_from_readable_sources(self):
        lines = [{'audit_event': 'ops_approval_signed', 'at': NOW - 5, 'target': 'apps.app', 'action': 'restart'},
                 {'audit_event': 'ops_approval_refused', 'at': NOW - 2, 'reason': 'passphrase_mismatch', 'request_id': 'x'},
                 {'audit_event': 'model_response_shape', 'at': NOW - 1, 'shape': {'top': ['choices']}}]
        result = make(audit_lines=lines).activity(10)
        self.assertEqual([e['kind'] for e in result['events']], ['blocked', 'approved', 'masked', 'approved', 'blocked'])
        self.assertEqual(len(make(audit_lines=lines).activity(3)['events']), 3)
        self.assertNotIn('request_id', walk(result))
        self.assertNotIn('approver', walk(result))

    def test_unreadable_source_is_reported_not_hidden(self):
        result = make({'/v1/snapshot': None, '/v1/activity': None}).activity()
        self.assertEqual((result['events'], result['sources']['redactor'], result['sources']['ops_timeline']), ([], 'unavailable', 'unavailable'))

    def test_limit_is_clamped(self):
        self.assertEqual(len(make().activity(99)['events']), 3)  # only three exist; the cap is console.MAX_EVENTS


class Explain(unittest.TestCase):
    topics = ('network', 'private-link', 'internet', 'redactor', 'gateway', 'audit')

    def test_shape_and_files(self):
        console_ = make(audit_lines=[{'audit_event': 'app_started', 'component': 'app', 'at': NOW, 'user': 'alpha'}])
        for topic in self.topics:
            with self.subTest(topic=topic):
                result = console_.explain(topic)
                self.assertEqual(set(result), {'topic', 'title', 'plain', 'how', 'proof', 'without', 'file'})
                self.assertTrue((REPO / result['file']).is_file(), result['file'])

    def test_live_proofs(self):
        c = make(audit_lines=[{'audit_event': 'app_started', 'component': 'app', 'at': NOW, 'user': 'alpha'}])
        network = c.explain('network')['proof']
        self.assertIn('default-deny', {p['name'] for p in network['namespaces']['apps']})
        self.assertEqual(network['unreadable'], ['agent-financial', 'agent-platform-guide'])
        self.assertEqual(c.explain('internet')['proof']['default_deny']['apps'], True)
        self.assertEqual(c.explain('redactor')['proof']['recent_masked'], 1)
        self.assertEqual(c.explain('gateway')['proof']['pods_ready'], 1)
        self.assertEqual(c.explain('audit')['proof']['line']['audit_event'], 'app_started')

    def test_proof_is_null_when_its_source_is_missing(self):
        c = make({}, audit_lines=[])
        for topic in self.topics:
            with self.subTest(topic=topic):
                self.assertIsNone(c.explain(topic)['proof'])

    def test_private_link_has_no_read_only_source(self):
        self.assertIsNone(make().explain('private-link')['proof'])

    def test_audit_proof_skips_bulky_shape_lines_and_nested_values(self):
        c = make(audit_lines=[{'audit_event': 'app_started', 'at': NOW}, {'audit_event': 'model_response_shape', 'shape': {'a': 1}}])
        self.assertEqual(c.explain('audit')['proof']['line']['audit_event'], 'app_started')
        c = make(audit_lines=[{'audit_event': 'x', 'at': NOW, 'nested': {'k': 'v'}}])
        self.assertNotIn('nested', c.explain('audit')['proof']['line'])

    def test_unknown_topic(self):
        self.assertIsNone(make().explain('nope'))

    def test_audit_ring_records_what_stdout_gets(self):
        import io
        before = len(audit.recent())
        audit.emit('console_test', 'app', stream=io.StringIO())
        self.assertEqual(len(audit.recent()), before)  # an explicit stream is not the process audit stream


class Leaks(unittest.TestCase):
    def test_no_secret_value_and_no_project_id_in_any_response(self):
        hostile = ops_answers()
        for f in hostile['/v1/snapshot']['findings'].values():  # the Pod's imageID is reduced to its digest in ops; double-check here
            f['facts']['image_digests'] = [DIGEST]
        c = make(hostile, audit_lines=[{'audit_event': 'app_started', 'component': 'app', 'at': NOW, 'user': 'alpha'}])
        bodies = [c.topology(), c.agents(), c.activity(20)] + [c.onboarding(n) for n in ('financial', 'platform-guide')] + \
                 [c.explain(t) for t in Explain.topics]
        for body in bodies:
            self.assertIsNone(LEAKS.search(walk(body)), LEAKS.search(walk(body)))

    def test_console_has_no_credential_or_kubernetes_client(self):
        source = (REPO / 'platform/core/src/agent_platform/console.py').read_text()
        for forbidden in ('master_key', 'ops_api_key', 'gateway_key', 'k8s', 'Client(', 'secrets/'):
            self.assertNotIn(forbidden, source)


class Http(unittest.TestCase):
    """The real handler on a loopback port: same Host/Origin boundary as the rest of the front door."""

    @classmethod
    def setUpClass(cls):
        cls.server = DemoServer(('127.0.0.1', 0), agents={})
        console.attach(cls.server, lambda path: ops_answers()[path])
        cls.server.console._clock = lambda: NOW
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path, headers=None):
        request = urllib.request.Request(self.server.origin + path, headers=headers or {})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
                return response.status, json.loads(response.read()), response.headers
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read()), error.headers

    def test_routes(self):
        for path in ('/api/console/topology', '/api/console/agents', '/api/console/activity?limit=3',
                     '/api/console/onboarding/financial', '/api/console/explain/network'):
            with self.subTest(path=path):
                status, body, headers = self.get(path)
                self.assertEqual(status, 200, body)
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.assertIsNone(LEAKS.search(json.dumps(body)))

    def test_unknown_names_are_404(self):
        for path in ('/api/console/onboarding/nope', '/api/console/onboarding/Financial', '/api/console/onboarding/..%2f..%2fetc',
                     '/api/console/explain/nope', '/api/console/explain/', '/api/console/other', '/api/console/topology/extra',
                     '/api/console/onboarding'):
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404)

    def test_bad_limit_is_400(self):
        for query in ('limit=abc', 'limit=-1', 'limit=100', 'limit=1&limit=2'):
            with self.subTest(query=query):
                self.assertEqual(self.get('/api/console/activity?' + query)[0], 400)

    def test_the_private_boundary_applies(self):
        self.assertEqual(self.get('/api/console/agents', {'Authorization': 'Bearer x'})[0], 403)
        self.assertEqual(self.get('/api/console/agents', {'X-Forwarded-For': '1.2.3.4'})[0], 403)
        self.assertEqual(self.get('/api/console/agents', {'Origin': 'http://evil.example'})[0], 403)

    def test_get_only(self):
        request = urllib.request.Request(self.server.origin + '/api/console/agents', data=b'{}', method='POST',
                                         headers={'Origin': self.server.origin, 'Content-Type': 'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5)
        self.assertEqual(caught.exception.code, 404)

    def test_existing_routes_still_served(self):
        self.assertEqual(self.get('/api/bootstrap')[0], 200)


class UiRoutes(Http):
    """The console UI and the two file-backed routes, through the same handler (inherits the server setup of Http)."""

    def raw(self, path, headers=None):
        request = urllib.request.Request(self.server.origin + path, headers=headers or {})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    def test_ui_files_are_served_with_a_csp_that_allows_only_own_fonts(self):
        status, body, headers = self.raw('/')
        self.assertEqual((status, headers['Content-Type']), (200, 'text/html; charset=utf-8'))
        self.assertIn(b'Agent Runtime Platform', body)
        csp = headers['Content-Security-Policy']
        self.assertIn("font-src 'self'", csp)
        self.assertIn("default-src 'none'", csp)
        self.assertNotIn('unsafe-inline', csp)
        self.assertNotRegex(csp, r'https?:')
        for path, kind in (('/style.css', 'text/css'), ('/core.js', 'text/javascript'), ('/map.js', 'text/javascript'),
                           ('/typeface/ibm-plex-mono-latin-400-normal.woff2', 'font/woff2')):
            status, body, headers = self.raw(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(headers['Content-Type'].startswith(kind), path)

    def test_only_existing_fixed_files_and_never_the_retired_demo_pages(self):
        for path in ('/operations.html', '/operations.js', '/i18n.json', '/app.css', '/typeface/nope.woff2', '/typeface/', '/typeface/../app.js',
                     '/typeface/LICENSE-barlow.txt', '/%2e%2e/etc/passwd', '/..%2fcore.js', '/typeface/a/b.woff2', '/.hidden.js', '/core.js/x'):
            with self.subTest(path=path):
                self.assertEqual(self.raw(path)[0], 404)

    def test_ui_files_obey_the_private_boundary(self):
        self.assertEqual(self.raw('/', {'X-Forwarded-For': '1.2.3.4'})[0], 403)
        self.assertEqual(self.raw('/core.js', {'Authorization': 'Bearer x'})[0], 403)

    def test_attacks_lists_closed_fields_from_the_results_file(self):
        status, body, _ = self.raw('/api/console/attacks')
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(data['available'])
        self.assertEqual(data['stopped'], sum(r['result'] == 'PASS' for r in data['results']))
        self.assertEqual(data['total'], len(data['results']))
        self.assertTrue(all(set(r) - {'note'} == {'case', 'result', 'at'} for r in data['results']))
        noted = [r for r in data['results'] if 'note' in r]
        self.assertTrue(all(r['result'] == 'FAIL' for r in noted))  # a note is attached only to the failed case it is about
        self.assertNotIn('financial_setup', {r['case'] for r in data['results']})  # a precondition, not an attack
        self.assertIsNone(LEAKS.search(body.decode()))

    def test_example_returns_the_shipped_manifest_and_its_command(self):
        data = json.loads(self.raw('/api/console/example')[1])
        self.assertTrue(data['available'])
        self.assertIn('budget_usd_month: 500.0', data['text'])
        self.assertEqual(data['command'], 'make onboard-check F=docs/examples/rejected-agent/agent.yaml')


class FileBackedRoutes(unittest.TestCase):
    def console_with(self, evidence, examples):
        c = make()
        c.evidence_dir, c.examples_dir = Path(evidence), Path(examples)
        return c

    def test_missing_or_malformed_results_file_is_an_honest_empty_state(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            c = self.console_with(tmp, tmp)
            c.live_attacks = Path(tmp) / 'absent.json'
            self.assertEqual(c.attacks(), {'available': False, 'source': None, 'file': 'docs/evidence/attack-suite.json', 'results': []})
            self.assertEqual(c.example(), {'available': False, 'file': 'docs/examples/rejected-agent/agent.yaml'})
            for bad in ('not json', '{}', json.dumps({'completed_at': 'x', 'results': [{'case': 'Bad Case!', 'result': 'PASS', 'at': 'x'}]}),
                        json.dumps({'completed_at': 'x', 'results': [{'case': 'ok_case', 'result': 'MAYBE', 'at': 'x'}]})):
                (Path(tmp) / 'attack-suite.json').write_text(bad)
                self.assertFalse(c.attacks()['available'], bad)

    def test_results_file_text_other_than_closed_fields_is_dropped(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'attack-suite.json').write_text(json.dumps({'completed_at': '2026-10-13T12:50:43+00:00', 'cluster': 'secret-name', 'results': [
                {'case': 'ok_case', 'result': 'PASS', 'at': '2026-10-13T12:00:00+00:00', 'evidence': {'password': 'hunter2'}}]}))
            data = self.console_with(tmp, tmp).attacks()
            self.assertEqual(data['results'], [{'case': 'ok_case', 'result': 'PASS', 'at': '2026-10-13T12:00:00+00:00'}])
            self.assertNotIn('hunter2', json.dumps(data))
            self.assertNotIn('secret-name', json.dumps(data))

    def test_agents_carry_the_port_and_redaction_the_ui_shows(self):
        by = {a['name']: a for a in make().agents()['agents']}
        self.assertEqual((by['financial']['port'], by['platform-guide']['port'], by['financial']['redaction']), (8081, 8082, 'required'))


class Packaging(unittest.TestCase):
    def test_image_ships_what_the_console_reads(self):
        dockerfile = (REPO / 'platform/core/images/Dockerfile').read_text()
        ignore = (REPO / 'platform/core/images/Dockerfile.dockerignore').read_text()
        app = dockerfile.split('FROM runtime AS app')[1].split('FROM runtime AS ops')[0]
        for copy in ('platform/core/kubernetes/', 'platform/agents/', 'platform/clouds/gke/kubernetes/'):
            self.assertIn('COPY --chown=65532:65532 ' + copy, app)
        ops = dockerfile.split('FROM runtime AS ops')[1]
        self.assertNotIn('platform/core/kubernetes', ops)  # the ops image does not carry the console data
        for copy in ('platform/core/ui/ /app/platform/ui/', 'docs/evidence/attack-suite*.json /app/platform/evidence/',
                     'docs/examples/rejected-agent/agent.yaml /app/platform/examples/rejected-agent/agent.yaml'):
            self.assertIn('COPY --chown=65532:65532 ' + copy, app)
        self.assertNotIn('/app/demo/ui', dockerfile)  # the qualified demo UI is no longer overlaid
        for allowed in ('!docs/evidence/attack-suite*.json', '!docs/examples/rejected-agent/agent.yaml', '!platform/core/ui/**'):
            self.assertIn(allowed, ignore)
        self.assertNotIn('!docs/**', ignore)
        for allowed in ('!platform/core/kubernetes/**', '!platform/agents/*/agent.yaml', '!platform/clouds/gke/kubernetes/gke.yaml'):
            self.assertIn(allowed, ignore)
        self.assertNotIn('!platform/agents/**', ignore)  # agent code and node_modules stay out of the app image

    def test_locate_resolves_the_repository_layout(self):
        kube, agents, gke = console.locate()
        self.assertEqual((kube, agents, gke), (KUBE, REPO / 'platform/agents', REPO / 'platform/clouds/gke/kubernetes'))


if __name__ == '__main__':
    unittest.main()
