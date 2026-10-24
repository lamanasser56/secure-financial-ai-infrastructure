"""Post-patch verification must check the authorized postcondition, not any healthy same-name object."""
import copy
import unittest

from agent_platform.ops import approval, diagnose
from agent_platform.ops.agent import Agent
from fixtures import FakeClient, REGISTRY, deployment, pod


class OpsVerificationRC1(unittest.TestCase):
    def execute(self, *, action='scale', drift=None):
        def apply(current, patch):
            current = copy.deepcopy(current)
            current['spec']['replicas'] = patch['spec'].get('replicas', current['spec']['replicas'])
            if 'template' in patch['spec']:
                current['spec']['template'].setdefault('metadata', {}).setdefault('annotations', {}).update(
                    patch['spec']['template']['metadata']['annotations'])
            current['metadata']['generation'] += 1
            if drift == 'uid': current['metadata']['uid'] = 'replacement'
            if drift == 'replicas': current['spec']['replicas'] = 1
            if drift == 'template': current['spec']['template']['spec']['containers'][0]['image'] = 'different-image'
            if drift == 'restart': current['spec']['template']['metadata']['annotations'].clear()
            desired = current['spec']['replicas']
            current['status'].update(observedGeneration=current['metadata']['generation'],
                                     replicas=desired, updatedReplicas=desired, availableReplicas=desired)
            return current
        client = FakeClient(deployment(available=0), pods=[pod(ready=False)], after_patch=apply)
        private, public = approval.generate_keypair()
        agent = Agent(client, {'apps.fault-demo': REGISTRY['apps.fault-demo']}, approval.Verifier(public),
                      verify_kwargs={'timeout': .03, 'interval': .001})
        finding = diagnose.diagnose(client.deployment, client.pods, [])
        proposal = agent.propose('apps.fault-demo', action, {'replicas': 2} if action == 'scale' else {}, finding)
        result = agent.execute(proposal['request_id'], approval.Signer(private).sign(proposal))
        self.assertEqual(len(client.patches), 1)
        return agent, proposal, result

    def test_uid_replacement_is_not_verified(self):
        self.assertEqual(self.execute(drift='uid')[2]['result'], 'NOT_VERIFIED')

    def test_replica_drift_is_not_verified(self):
        self.assertEqual(self.execute(drift='replicas')[2]['result'], 'NOT_VERIFIED')

    def test_template_change_is_not_verified(self):
        self.assertEqual(self.execute(drift='template')[2]['result'], 'NOT_VERIFIED')

    def test_missing_restart_annotation_is_not_verified(self):
        self.assertEqual(self.execute(action='restart', drift='restart')[2]['result'], 'NOT_VERIFIED')

    def test_approved_scale_and_restart_still_verify_and_emit_matching_stage(self):
        for action in ('scale', 'restart'):
            with self.subTest(action=action):
                agent, proposal, result = self.execute(action=action)
                self.assertEqual(result['result'], 'VERIFIED')
                self.assertEqual(agent.timeline[-1]['stage'], 'verified')
                self.assertEqual(agent.timeline[-1]['request_id'], proposal['request_id'])
