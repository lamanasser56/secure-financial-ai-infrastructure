"""Current rendered observation inventory, incomplete scans and unchanged mutation boundaries."""
import contextlib
import io
from pathlib import Path
import tempfile
import time
import unittest

import yaml
from agent_platform.boundary_http import Rejected
from agent_platform.ops import approval, authority, registry
from agent_platform.ops.agent import Agent
from agent_platform.ops.executor import Executor, ReplayStore
from fixtures import FakeClient, REGISTRY, deployment, pod
from test_console import KubeStub, checked_posture, make, ops_answers

ROOT = Path(__file__).resolve().parents[3]
BOUNDARIES = {'platform.gateway-boundary', 'apps.financial-frontdoor', 'ops.ops-executor'}


def core_targets():
    config = next(d for d in yaml.safe_load_all((ROOT/'platform/core/kubernetes/ops/workloads.yaml').read_text())
                  if d['kind']=='ConfigMap' and d['metadata']['name']=='ops-agent-registry')
    return config['data'], registry.parse(config['data'])


def mutable_authority():
    return {doc['metadata']['namespace']+'.'+name
            for doc in authority.declaration()['core'] if doc['kind']=='Role'
            for rule in doc['rules'] if 'patch' in rule['verbs'] and 'deployments' in rule['resources']
            for name in rule['resourceNames']}


class CurrentObservationInventory(unittest.TestCase):
    def test_core_registry_declares_three_new_read_only_targets_and_preserves_four_mutable_targets(self):
        config, targets = core_targets()
        self.assertEqual({k for k, t in targets.items() if t.observe_only}, BOUNDARIES)
        self.assertEqual({k for k, t in targets.items() if not t.observe_only}, mutable_authority())
        for key in BOUNDARIES:
            self.assertEqual({f for f in config if f.startswith(key+'.')}, {key+'.observe'})
        for key in BOUNDARIES:
            broken = dict(config, **{key+'.min':'0', key+'.max':'1', key+'.health':'none'})
            with self.assertRaises(ValueError): registry.parse(broken)
            broken = dict(config, **{key+'.observe':'mutable'})
            with self.assertRaises(ValueError): registry.parse(broken)

    def test_ops_namespace_reads_are_declared_once_and_have_no_mutation_or_secret_access(self):
        docs = authority.inventory({'ops':['ops-executor']})
        role = docs[('Role','ops','ops-agent-observe')]
        for rule in role['rules']:
            self.assertLessEqual(set(rule['verbs']), {'get','list','watch'})
            self.assertFalse(set(rule['resources']) & {'secrets','pods/exec','pods/attach'})
        binding = docs[('RoleBinding','ops','ops-agent-observe')]
        self.assertEqual(binding['subjects'], [{'kind':'ServiceAccount','name':'ops-agent','namespace':'ops'}])
        self.assertEqual(binding['roleRef']['name'], role['metadata']['name'])
        self.assertEqual((ROOT/'platform/core/kubernetes/policies/ops-agent-rbac.yaml').read_text(), authority.core_manifest())

    def test_scan_of_each_new_target_cannot_propose_or_call_a_model(self):
        _, targets = core_targets()
        for key in BOUNDARIES:
            with self.subTest(target=key), contextlib.redirect_stdout(io.StringIO()):
                client = FakeClient(deployment(available=0), [pod(ready=False)])
                calls = []
                agent = Agent(client, {key: targets[key]}, None, explainer=lambda value: calls.append(value))
                agent.scan()
                self.assertEqual(agent.snapshot()['pending'], [])
                self.assertEqual(agent.findings[key]['owner_action'], 'NOTIFY_PLATFORM_OWNER')
                self.assertEqual((calls, client.patches), ([], []))
                with self.assertRaises(approval.ApprovalDenied): agent.propose(key, 'restart', {}, agent.findings[key])

    def test_executor_refuses_a_valid_owner_signature_for_an_observe_only_target(self):
        _, targets = core_targets()
        private, public = approval.generate_keypair()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            client = FakeClient(deployment(available=0), [pod(ready=False)])
            producer = Agent(client, {'apps.fault-demo':REGISTRY['apps.fault-demo']}, None)
            producer.scan()
            sample = next(p for p in producer.snapshot()['pending'] if p['action']=='restart')
            executor = Executor(client, targets, public, 'e'*64, replay_store=ReplayStore(Path(directory)/'nonces.sqlite'))
            for key in BOUNDARIES:
                proposal = dict(sample, target=key)
                signed = approval.Signer(private).sign(proposal)
                with self.assertRaisesRegex(Rejected, 'PROPOSAL_REJECTED'):
                    executor.handle('/execute', 'Bearer '+'e'*64, {'proposal':proposal,'approval':signed})
            self.assertEqual(client.patches, [])


class ScanCompleteness(unittest.TestCase):
    def test_current_rendered_rbac_including_executor_and_observer_ops_namespace_is_clean(self):
        _, targets = core_targets()
        from agent_platform import onboarding
        observed = onboarding.render_ops_observe(onboarding.load_all())[0]['data']
        targets.update(registry.parse_observe(observed))
        at = time.time()
        scan = Agent(KubeStub(), targets, None, clock=lambda:at).posture()
        self.assertIn('ops',scan['namespaces'])
        self.assertEqual((scan['complete'],scan['clean'],scan['findings'],scan['unreadable']), (True,True,[],[]))
        self.assertEqual((scan['checked_at'],scan['source']), (round(at,3),'ops-agent /v1/posture'))

    def test_scan_timestamps_cover_the_whole_read_window_and_publish_one_freshness_contract(self):
        from agent_platform.observations import FRESH_SECONDS
        _, targets = core_targets()
        ticks = iter((1000.0, 1300.0))
        scan = Agent(KubeStub(), targets, None, clock=lambda:next(ticks)).posture()
        self.assertEqual((scan['started_at'],scan['checked_at'],scan['max_age_seconds']), (1000.0,1300.0,FRESH_SECONDS))

    def test_every_failed_list_marks_scan_incomplete_but_readable_network_facts_survive(self):
        for kind in ('pods','events','roles','rolebindings','networkpolicies'):
            with self.subTest(kind=kind):
                result = checked_posture(KubeStub(forbidden_kinds=(kind,)), ['agent-financial'])
                self.assertFalse(result['complete'])
                self.assertFalse(result['clean'])
                self.assertEqual(result['unreadable'], ['agent-financial'])
                if kind!='networkpolicies': self.assertIn('agent-financial',result['network'])

    def test_selected_release_lists_actual_workers_and_core_observation_targets(self):
        console=make()
        agents={a['name']:a for a in console.agents()['agents']}
        self.assertEqual({w['target_id'] for w in agents['financial']['workloads']},
                         {'agent-financial.agent-u'+str(i) for i in range(1,4)})
        self.assertTrue(BOUNDARIES <= {w['target_id'] for w in agents['ops-agent']['watched_targets']})
        self.assertEqual({t['target'] for t in agents['ops-agent']['targets']},mutable_authority())

    def test_one_scaled_down_or_missing_worker_cannot_make_the_logical_agent_healthy(self):
        for missing in (False,True):
            answers=ops_answers()
            findings=answers['/v1/snapshot']['findings']
            if missing: del findings['agent-financial.agent-u3']
            else:
                worker=findings['agent-financial.agent-u3']
                worker.update(desired_replicas=0,available_replicas=0)
                worker['facts'].update(pods_ready=0,pods_total=0)
            console=make(answers)
            agent=next(a for a in console.agents()['agents'] if a['name']=='financial')
            self.assertEqual(agent['live']['desired'],3)
            self.assertEqual(agent['live']['state'],'DEGRADED')
            self.assertEqual(agent['health']['state'],'not_ready')


if __name__=='__main__': unittest.main()
