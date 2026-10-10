"""Security & Operations Agent: observe -> diagnose -> propose -> (owner approves) -> execute once -> verify -> audit.

The model is optional and only explains a finding from redacted, structured facts; it never selects targets
or actions. Logs and model text are untrusted data: they are never interpreted as instructions.
"""
import collections
import threading
import time
import uuid

from agent_platform import audit
from agent_platform.k8s import KubeError
from agent_platform.ops import actions, approval, diagnose, posture
from agent_platform.ops.registry import ACTIONS

STAGES = ('observed', 'diagnosed', 'proposed', 'approved', 'executed', 'verified', 'denied', 'failed')


class Agent:
    def __init__(self, client, targets, verifier, *, explainer=None, clock=time.time, verify_kwargs=None):
        self.client, self.targets, self.verifier = client, targets, verifier
        self.explainer, self.clock = explainer, clock
        self.timeline = collections.deque(maxlen=200)
        self.denials = collections.deque(maxlen=100)
        self.proposals, self.findings = {}, {}
        self._lock = threading.Lock()
        self._verify_kwargs = verify_kwargs or {}

    def record(self, stage, target, **fields):
        event = {'id': str(uuid.uuid4()), 'stage': stage, 'target': target, 'at': round(self.clock(), 3), **fields}
        with self._lock:
            self.timeline.append(event)
            if stage == 'denied':
                self.denials.append(event)
        audit.emit('ops_' + stage, 'ops-agent', target=target, **{k: v for k, v in fields.items() if k != 'explanation'})
        return event

    # observe + diagnose ----------------------------------------------------------------------------------
    def observe(self, key):
        target = self.targets[key]
        deployment = self.client.get('deployments', target.namespace, target.name)
        selector = ','.join(f'{k}={v}' for k, v in sorted(deployment['spec']['selector']['matchLabels'].items()))
        pods = self.client.list('pods', target.namespace, selector)
        events = self.client.list('events', target.namespace)
        return deployment, pods, events

    def scan(self):
        results = {}
        for key in self.targets:
            try:
                deployment, pods, events = self.observe(key)
            except KubeError as error:
                self.record('failed', key, code='OBSERVE_' + str(error.status))
                continue
            finding = diagnose.diagnose(deployment, pods, events)
            previous = self.findings.get(key)
            self.findings[key] = finding
            if previous is None or previous['evidence_digest'] != finding['evidence_digest']:
                self.record('observed', key, pods=len(pods), available=finding['available_replicas'], desired=finding['desired_replicas'])
                self.record('diagnosed', key, finding=finding['finding'], evidence_digest=finding['evidence_digest'])
                if finding['finding'] != 'HEALTHY':
                    for action in finding['suggested_actions']:
                        arguments = {'replicas': min(self.targets[key].max_replicas, finding['desired_replicas'] + 1)} if action == 'scale' else {}
                        self.propose(key, action, arguments, finding)
            results[key] = finding['finding']
        return results

    def propose(self, key, action, arguments, finding):
        if key not in self.targets or action not in ACTIONS:
            self.record('denied', key, code='NOT_REGISTERED_OR_NOT_ALLOWLISTED', action=action)
            raise approval.ApprovalDenied('NOT_REGISTERED_OR_NOT_ALLOWLISTED')
        proposal = {'request_id': str(uuid.uuid4()), 'target': key, 'action': action, 'arguments': arguments,
                    'args_digest': approval.args_digest(arguments), 'evidence_digest': finding['evidence_digest'],
                    'finding': finding['finding'], 'created_at': round(self.clock(), 3), 'state': 'proposed'}
        if self.explainer is not None:
            proposal['explanation'] = self.explainer(finding)  # untrusted text, display only
        with self._lock:
            self.proposals[proposal['request_id']] = proposal
        self.record('proposed', key, request_id=proposal['request_id'], action=action, finding=finding['finding'])
        return proposal

    # execute (single attempt) + verify --------------------------------------------------------------------
    def execute(self, request_id, token):
        with self._lock:
            proposal = self.proposals.get(request_id)
            if proposal is None or proposal['state'] != 'proposed':
                proposal = None
        if proposal is None:
            self.record('denied', None, code='UNKNOWN_OR_USED_REQUEST', request_id=request_id)
            return {'result': 'DENIED', 'code': 'UNKNOWN_OR_USED_REQUEST'}
        key = proposal['target']
        try:
            claims = self.verifier.consume(token, proposal)
        except approval.ApprovalDenied as denied:
            self.record('denied', key, code=denied.code, request_id=request_id)
            return {'result': 'DENIED', 'code': denied.code}
        current = self.findings.get(key)
        if current is None or current['evidence_digest'] != proposal['evidence_digest']:
            proposal['state'] = 'stale'
            self.record('denied', key, code='EVIDENCE_CHANGED', request_id=request_id)
            return {'result': 'DENIED', 'code': 'EVIDENCE_CHANGED'}
        proposal['state'] = 'approved'
        self.record('approved', key, request_id=request_id, approver=claims['approver'])
        target = self.targets[key]
        try:
            deployment = self.client.get('deployments', target.namespace, target.name)
            replicasets = self.client.list('replicasets', target.namespace) if proposal['action'] == 'rollback' else []
            patch, expected = actions.plan(proposal['action'], target, deployment, replicasets, proposal['arguments'])
            self.client.patch_deployment(target.namespace, target.name, patch)  # exactly one attempt
        except actions.ActionRejected as rejected:
            proposal['state'] = 'failed'
            self.record('failed', key, code=rejected.code, request_id=request_id)
            return {'result': 'FAILED', 'code': rejected.code}
        except KubeError as error:
            proposal['state'] = 'failed'
            code = 'ADMISSION_REJECTED' if error.status in (400, 403, 422) else 'API_' + str(error.status)
            self.record('denied' if code == 'ADMISSION_REJECTED' else 'failed', key, code=code, request_id=request_id)
            return {'result': 'FAILED', 'code': code}
        proposal['state'] = 'executed'
        self.record('executed', key, request_id=request_id, action=proposal['action'])
        outcome = actions.verify(self.client, target, expected, **self._verify_kwargs)
        proposal['state'] = 'verified' if outcome['verified'] else 'not_verified'
        self.record('verified' if outcome['verified'] else 'failed', key, request_id=request_id, code=outcome['code'])
        return {'result': 'VERIFIED' if outcome['verified'] else 'NOT_VERIFIED', 'code': outcome['code']}

    def posture(self):
        return posture.check(self.client, sorted({t.namespace for t in self.targets.values()}))

    def snapshot(self):
        with self._lock:
            return {'timeline': list(self.timeline)[-50:], 'denials': list(self.denials)[-20:],
                    'pending': [p for p in self.proposals.values() if p['state'] == 'proposed'],
                    'findings': dict(self.findings)}
