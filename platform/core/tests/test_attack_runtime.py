"""Current live-probe protocol: real HTTP, real frontdoor-issued active capabilities, no provider or cluster."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import datetime
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'clouds/gke'))
from attack_fixture_spec import MONTH
from attack_probes.financial_probe import Probe, http  # noqa: E402
from attack_runtime import active_pair, NotExercised, RestoreFailed, temporary_worker, temporary_scale  # noqa: E402
import attack_suite  # noqa: E402
from agent_platform.boundary_http import Server  # noqa: E402
from agent_platform.data_capability import CapabilityIssuer  # noqa: E402
from agent_platform.ops.approval import generate_keypair  # noqa: E402
from finance_agent.data_broker import DataBroker  # noqa: E402
from finance_agent.frontdoor import Forwarder  # noqa: E402

USERS = ('00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002')
MARKERS = ('Cafe Nadia', 'Sara Gold Jewellery')


class Store:
    def __init__(self): self.users = []
    def read(self, user, statement, params):
        self.users.append(user)
        index = USERS.index(user)
        return [(index + 1, datetime.date(2035, 11, 2), MARKERS[index], 'food', 2450, '')]


class HttpProbe(unittest.TestCase):
    def setUp(self):
        private, public = generate_keypair()
        self.private, self.public = private, public
        self.issuer = CapabilityIssuer(private, public)
        self.servers, self.threads, self.store = [], [], Store()
        broker = DataBroker(self.store, self.issuer, {'worker-a': 'a'*64, 'worker-b': 'b'*64},
            user_bindings={'worker-a': USERS[0], 'worker-b': USERS[1]}, audit_key=b'x'*32)
        url = self.serve(broker)
        self.configs = [{'agent_name': name, 'user_id': user, 'broker_key': key*64,
            'worker_key': auth*64, 'capability_public_key': public, 'gateway_key': 'g'*64, 'redactor_key': 'r'*64} for name, user, key, auth in
            (('worker-a', USERS[0], 'a', 'c'), ('worker-b', USERS[1], 'b', 'd'))]
        self.probes = [Probe(c, broker=url + '/tools', hold=5) for c in self.configs]
        self.urls = [self.serve(probe) for probe in self.probes]
        self.frontdoor = Forwarder(self.issuer, {user: {'agent': c['agent_name'], 'key': c['worker_key'], 'url': target + '/ask'}
            for user, c, target in zip(USERS, self.configs, self.urls)})

    def serve(self, service):
        server = Server(('127.0.0.1', 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append(server); self.threads.append(thread)
        return 'http://127.0.0.1:' + str(server.server_port)

    def tearDown(self):
        for probe in self.probes: probe.finished.set()
        for server in reversed(self.servers): server.shutdown(); server.server_close()
        for thread in self.threads: thread.join(2)

    def control(self, index, value):
        status, result = http(self.urls[index] + '/probe', self.configs[index]['worker_key'], value)
        if status != 200: raise NotExercised('control_failed')
        return result

    def test_two_real_frontdoor_turns_prove_active_own_and_foreign_capability_controls(self):
        ok, evidence = active_pair(lambda i: self.frontdoor.ask(USERS[i], 'Synthetic broker probe.', 'en'),
            self.control, self.control, timeout=3)
        self.assertTrue(ok, evidence)
        self.assertEqual(self.issuer.active, {})
        for summary in evidence['workers']:
            self.assertEqual(summary['verdict'], 'PASS')
            self.assertTrue(all(summary['checks'].values()))
        self.assertEqual(self.store.users.count(USERS[0]), 2)
        self.assertEqual(self.store.users.count(USERS[1]), 2)
        raw = json.dumps(evidence)
        for private in (*USERS, *MARKERS, *[c['broker_key'] for c in self.configs], 'capability', 'BEGIN'):
            # One fixed check label mentions capability; no token or identity value is present.
            if private != 'capability': self.assertNotIn(private, raw)

    def test_detached_issuer_or_revoked_tokens_cannot_replace_positive_live_control(self):
        token, claims = self.issuer.issue(USERS[0], 'worker-a')
        self.issuer.revoke(claims)
        summary = self.probes[0].exercise(token, {'foreign': token, 'own_marker': MARKERS[0], 'foreign_marker': MARKERS[1], 'month':MONTH})
        self.assertEqual(summary['verdict'], 'NOT_EXERCISED')
        self.assertFalse(summary['checks']['own_before'])
        self.assertEqual(self.store.users, [])
        detached = CapabilityIssuer(self.private, self.public)
        token, _ = detached.issue(USERS[0], 'worker-a')
        summary = self.probes[0].exercise(token, {'foreign': token, 'own_marker': MARKERS[0], 'foreign_marker': MARKERS[1], 'month':MONTH})
        self.assertEqual(summary['verdict'], 'NOT_EXERCISED')
        self.assertEqual(self.store.users, [])

    def test_transport_failure_never_becomes_a_rejected_attack(self):
        self.probes[0].dispatch = lambda *args: (0, {'code': 'TRANSPORT_ERROR'})
        token, _ = self.issuer.issue(USERS[0], 'worker-a')
        summary = self.probes[0].exercise(token, {'foreign': token, 'own_marker': MARKERS[0], 'foreign_marker': MARKERS[1], 'month':MONTH})
        self.assertEqual(summary['verdict'], 'NOT_EXERCISED')

    def test_a_boundary_that_accepts_a_foreign_token_fails_the_probe(self):
        original = self.probes[0].dispatch
        token, _ = self.issuer.issue(USERS[0], 'worker-a')
        foreign, _ = self.issuer.issue(USERS[1], 'worker-b')
        def broken(url, key, body):
            if body['capability'] == foreign:
                return 200, {'transactions': [{'merchant': MARKERS[1]}]}
            return original(url, key, body)
        self.probes[0].dispatch = broken
        summary = self.probes[0].exercise(token, {'foreign': foreign, 'own_marker': MARKERS[0], 'foreign_marker': MARKERS[1], 'month':MONTH})
        self.assertEqual(summary['verdict'], 'FAIL')

    def test_visible_cross_user_data_is_a_failure_even_when_own_control_is_wrong(self):
        token,_=self.issuer.issue(USERS[0],'worker-a')
        self.probes[0].dispatch=lambda *args:(200,{'transactions':[{'merchant':MARKERS[1]}]})
        summary=self.probes[0].exercise(token,{'foreign':token,'own_marker':MARKERS[0],'foreign_marker':MARKERS[1],'month':MONTH})
        self.assertEqual(summary['verdict'],'FAIL')

    def test_operator_channel_has_no_unauthenticated_capability_endpoint(self):
        status, _ = http(self.urls[0] + '/probe', 'wrong'*10, {'operation': 'active'})
        self.assertEqual(status, 403)

    def test_coordinator_releases_both_turns_on_an_exercise_failure(self):
        finished = []
        def inspect(index, body):
            if body['operation'] == 'exercise': raise NotExercised('synthetic_test_failure')
            return self.control(index, body)
        def finish(index, body):
            finished.append(index)
            return self.control(index, body)
        with self.assertRaises(NotExercised):
            active_pair(lambda i: self.frontdoor.ask(USERS[i], 'Synthetic probe.', 'en'), inspect, finish, timeout=3)
        self.assertEqual(finished, [0, 1])
        self.assertEqual(self.issuer.active, {})


class Kube:
    def __init__(self):
        self.doc = {'metadata': {'uid': 'original-worker'}, 'spec': {'replicas': 3, 'template': {'metadata': {'labels': {'app': 'worker'}},
            'spec': {'containers': [{'name': 'worker', 'image': 'signed@sha256:' + 'b'*64,
                'command': ['python', '-m', 'finance_agent.worker'], 'args': ['kept']}], 'serviceAccountName': 'original'}}}}
        self.rollouts, self.fail_first, self.patches = 0, False, []
    def __call__(self, *args, input=None):
        if 'get' in args: return SimpleNamespace(returncode=0, stdout=json.dumps(self.doc))
        if 'patch' in args:
            body = json.loads(args[args.index('-p') + 1])
            self.patches.append(body)
            field = body[1]['path'].rsplit('/', 1)[-1]
            if body[0]['value'] != self.doc['metadata']['uid'] or body[1]['value'] != self.doc['spec'][field]:
                return SimpleNamespace(returncode=1)
            self.doc['spec'][field] = body[2]['value']
            return SimpleNamespace(returncode=0)
        self.rollouts += 1
        return SimpleNamespace(returncode=int(self.fail_first and self.rollouts == 1))


class Restoration(unittest.TestCase):
    def test_scaling_restores_the_original_count_instead_of_assuming_one(self):
        kube = Kube()
        with self.assertRaises(NotExercised):
            with temporary_scale(kube, 'platform', 'redactor', 0):
                self.assertEqual(kube.doc['spec']['replicas'], 0)
                raise NotExercised('synthetic_outage')
        self.assertEqual(kube.doc['spec']['replicas'], 3)

    def test_scaling_cannot_overwrite_a_concurrent_operator_change(self):
        kube = Kube()
        with self.assertRaises(RestoreFailed):
            with temporary_scale(kube, 'platform', 'redactor', 0):
                kube.doc['spec']['replicas'] = 5
        self.assertEqual(kube.doc['spec']['replicas'], 5)

    def test_original_template_is_restored_after_success_and_exception(self):
        for fail in (False, True):
            kube = Kube(); before = deepcopy(kube.doc)
            try:
                with temporary_worker(kube, 'agent-financial', 'agent-u1', 'synthetic probe source'):
                    self.assertEqual(kube.doc['spec']['template']['spec']['containers'][0]['image'], before['spec']['template']['spec']['containers'][0]['image'])
                    if fail: raise NotExercised('synthetic')
            except NotExercised:
                self.assertTrue(fail)
            self.assertEqual(kube.doc, before)
            self.assertEqual(kube.rollouts, 2)

    def test_failed_probe_rollout_still_restores_original_worker(self):
        kube = Kube(); before = deepcopy(kube.doc); kube.fail_first = True
        with self.assertRaises(NotExercised):
            with temporary_worker(kube, 'agent-financial', 'agent-u1', 'synthetic'): pass
        self.assertEqual(kube.doc, before)

    def test_concurrent_owner_change_is_never_overwritten(self):
        kube = Kube()
        with self.assertRaises(RestoreFailed):
            with temporary_worker(kube, 'agent-financial', 'agent-u1', 'synthetic'):
                kube.doc['spec']['template']['metadata']['labels']['operator-change'] = 'retain'
        self.assertEqual(kube.doc['spec']['template']['metadata']['labels']['operator-change'], 'retain')


class CurrentSuite(unittest.TestCase):
    def test_all_model_cases_refuse_infrastructure_or_empty_replies(self):
        class App:
            def __init__(self, reply): self.reply = reply
            def ask(self, *args): return self.reply
            def call(self, *args, **kwargs): return 200, {'expenses': [{'merchant': attack_suite.EVASIVE}]}, None
        for name in ('case_show_saras_expenses', 'case_prompt_injection_question', 'case_filter_bypass_merchant',
                     'case_ungrounded_claim', 'case_merchant_with_digits'):
            for reply in ({}, {'status': 'blocked', 'reason': 'model_unavailable'},
                          {'status': 'blocked', 'reason': 'redaction_unavailable'}, {'status': 'refused', 'reason': 'rate_limited'},
                          {'error': 'sign_in_required'}, {'status': 'answered', 'answer': ''}):
                with self.subTest(case=name, reply=reply), self.assertRaises(NotExercised):
                    getattr(attack_suite, name)(App(reply), ('synthetic-cookie', 'synthetic-csrf'))

    def test_financial_transport_targets_the_current_frontdoor(self):
        app = attack_suite.Financial.__new__(attack_suite.Financial)
        app.call = lambda *args: (200, {}, None)
        with patch.object(attack_suite.subprocess, 'Popen') as popen, patch.object(attack_suite.time, 'sleep'):
            popen.return_value.poll.return_value = None
            app.connect()
        args = popen.call_args.args[0]
        self.assertEqual(args[args.index('-n') + 1], 'apps')
        self.assertIn('deployment/financial-frontdoor', args)
        self.assertNotIn('deployment/agent', args)
        self.assertIn(str(app.local_port) + ':8081', args)
        self.assertNotIn('8081:8081', args)

    def test_session_epoch_restart_changes_only_the_actual_session_owner(self):
        app = Mock()
        app.call.side_effect = [(200, {}, None), (401, {}, None), (200, {}, None)]
        app.login.return_value = ('fresh-cookie', 'fresh-csrf')
        calls = []
        def kube(*args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0)
        with patch.object(attack_suite, 'session_pods', side_effect=[['old'], ['new']]), patch.object(attack_suite, 'k', side_effect=kube):
            ok, _ = attack_suite.case_session_epoch_restart(app, ('old-cookie', 'old-csrf'))
        self.assertTrue(ok)
        app.reconnect.assert_called_once_with('pod/new')
        self.assertTrue(all(args[1] == 'apps' for args in calls))
        self.assertIn(('-n', 'apps', 'rollout', 'restart', 'deployment/financial-frontdoor'), calls)


if __name__ == '__main__':
    unittest.main()
