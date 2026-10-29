"""Security & Operations Agent: observe -> diagnose -> propose -> (owner approves) -> execute once -> verify -> audit.

The model is optional and only explains a finding from redacted, structured facts; it never selects targets
or actions. Logs and model text are untrusted data: they are never interpreted as instructions.

Execution re-checks the live object: after the one-use approval is consumed, the agent GETs the Deployment, its Pods
and events again, re-diagnoses, and requires the same UID, evidence digest and resourceVersion; the patch then carries
the approved resourceVersion as a precondition, so a change between that GET and the PATCH is a 409, not a mutation.
A request that fails these checks is consumed and marked stale. Pending proposals expire with the approval lifetime,
a newer proposal for the same target supersedes older pending ones, and the proposal history is bounded.
"""
import collections
import copy
import re
import threading
import time
import uuid

from agent_platform import audit
from agent_platform.observations import FRESH_SECONDS
from agent_platform.k8s import KubeError
from agent_platform.ops import actions, activity, approval, diagnose, posture
from agent_platform.ops.registry import ACTIONS

STAGES = ('observed', 'diagnosed', 'proposed', 'approved', 'executed', 'verified', 'denied', 'failed')
PROPOSAL_TTL = approval.MAX_TTL  # a pending proposal lives as long as one approval may
MAX_PROPOSALS = 100  # proposals kept (pending + history); the oldest finished ones are dropped first
REQUEST_ID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}')  # the uuid4 propose() issues


class Agent:
    def __init__(self, client, targets, verifier, *, explainer=None, clock=time.time, verify_kwargs=None,
                 executor=None, component='ops-agent'):
        self.client, self.targets, self.verifier = client, targets, verifier
        self.explainer, self.clock = explainer, clock
        self.timeline = collections.deque(maxlen=200)
        self.denials = collections.deque(maxlen=100)
        self.proposals, self.findings = {}, {}
        self._explanations = {}  # (target, finding, revision) -> explanation: one model call per episode
        self._lock = threading.Lock()
        self._verify_kwargs = verify_kwargs or {}
        self.executor, self.component = executor, component

    def record(self, stage, target, **fields):
        event = {'id': str(uuid.uuid4()), 'stage': stage, 'target': target, 'at': round(self.clock(), 3), **fields}
        with self._lock:
            self.timeline.append(event)
            if stage == 'denied':
                self.denials.append(event)
        audit.emit('ops_' + stage, self.component, target=target, **{k: v for k, v in fields.items() if k != 'explanation'})
        return event

    # observe + diagnose ----------------------------------------------------------------------------------
    def observe(self, key):
        target = self.targets[key]
        deployment = self.client.get('deployments', target.namespace, target.name)
        selector = ','.join(f'{k}={v}' for k, v in sorted(deployment['spec']['selector']['matchLabels'].items()))
        pods = diagnose.live_pods(self.client.list('pods', target.namespace, selector))  # terminating Pods are not counted
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
            finding['facts'] = dict(diagnose.live_facts(pods), observed_at=round(self.clock(), 3))  # not part of evidence_digest
            previous = self.findings.get(key)
            if previous is not None and previous['evidence_digest'] == finding['evidence_digest'] and 'explanation' in previous:
                finding['explanation'] = previous['explanation']
            self.findings[key] = finding
            if self.targets[key].observe_only:  # read-only monitoring: no proposal, no explanation, no change
                finding['suggested_actions'], finding['automated_fix'] = [], False
                finding['owner_action'] = None if finding['finding'] == 'HEALTHY' else (
                    'NOTIFY_AGENT_TEAM' if self.targets[key].namespace.startswith('agent-') else 'NOTIFY_PLATFORM_OWNER')
                finding['observe_only'] = True
            changed = previous is None or previous['evidence_digest'] != finding['evidence_digest']
            if (not changed and not self.targets[key].observe_only and finding['suggested_actions']
                    and not self._pending_for(key, finding)):
                # Same evidence, but no live proposal for this exact object (expired, or the Deployment's
                # resourceVersion moved): propose again so an approval can still apply.
                for action in finding['suggested_actions']:
                    self.propose(key, action, self._arguments(key, action, finding), finding)
            if changed:
                self._supersede(key, lambda p: p['evidence_digest'] != finding['evidence_digest'])
                self.record('observed', key, pods=len(pods), available=finding['available_replicas'], desired=finding['desired_replicas'])
                self.record('diagnosed', key, finding=finding['finding'], evidence_digest=finding['evidence_digest'])
                if self.targets[key].observe_only:
                    pass
                elif finding['finding'] == 'HEALTHY':
                    self._explanations = {k: v for k, v in self._explanations.items() if k[0] != key}
                elif not finding['suggested_actions']:
                    # No automated fix (the fix needs a Pod spec change): diagnose, explain and recommend an owner action.
                    explanation = self.explain(key, finding)
                    if explanation is not None:
                        finding['explanation'] = explanation  # untrusted text, display only
                else:
                    for action in finding['suggested_actions']:
                        self.propose(key, action, self._arguments(key, action, finding), finding)
            results[key] = finding['finding']
        return results

    def _arguments(self, key, action, finding):
        return {'replicas': min(self.targets[key].max_replicas, finding['desired_replicas'] + 1)} if action == 'scale' else {}

    def _expire(self):
        """Caller holds the lock: expire old pending proposals and bound the history."""
        now = self.clock()
        for p in self.proposals.values():
            if p['state'] == 'proposed' and now >= p['expires_at']:
                p['state'] = 'expired'
        for request_id in [r for r, p in self.proposals.items() if p['state'] != 'proposed'][:max(0, len(self.proposals) - MAX_PROPOSALS)]:
            del self.proposals[request_id]

    def _pending_for(self, key, finding):
        with self._lock:
            self._expire()
            return any(p['target'] == key and p['state'] == 'proposed' and p['evidence_digest'] == finding['evidence_digest']
                       and p['uid'] == finding.get('uid') and p['resource_version'] == finding.get('resource_version')
                       for p in self.proposals.values())

    def _supersede(self, key, matches):
        """Mark this target's matching pending proposals stale (a newer finding or proposal replaces them)."""
        with self._lock:
            older = [p for p in self.proposals.values() if p['target'] == key and p['state'] == 'proposed' and matches(p)]
            for p in older:
                p['state'] = 'stale'
        for p in older:
            self.record('denied', key, code='SUPERSEDED', request_id=p['request_id'])

    def propose(self, key, action, arguments, finding):
        if key not in self.targets or action not in ACTIONS or self.targets[key].observe_only:
            self.record('denied', key, code='NOT_REGISTERED_OR_NOT_ALLOWLISTED', action=action)
            raise approval.ApprovalDenied('NOT_REGISTERED_OR_NOT_ALLOWLISTED')
        proposal = {'request_id': str(uuid.uuid4()), 'target': key, 'action': action, 'arguments': arguments,
                    'args_digest': approval.args_digest(arguments), 'evidence_digest': finding['evidence_digest'],
                    'uid': finding.get('uid'), 'resource_version': finding.get('resource_version'),
                    'finding': finding['finding'], 'created_at': round(self.clock(), 3),
                    'expires_at': round(self.clock() + PROPOSAL_TTL, 3), 'state': 'proposed'}
        explanation = self.explain(key, finding)
        if explanation is not None:
            proposal['explanation'] = explanation  # untrusted text, display only
        self._supersede(key, lambda p: p['action'] == action)  # older evidence or object: no longer approvable
        with self._lock:
            self.proposals[proposal['request_id']] = proposal
            self._expire()
        self.record('proposed', key, request_id=proposal['request_id'], action=action, finding=finding['finding'])
        return proposal

    def explain(self, key, finding):
        """One model explanation per fault episode (target, finding, revision), not per proposal or evidence change, so
        a crash loop cannot turn into an unbounded number of model requests."""
        if self.explainer is None:
            return None
        episode = (key, finding['finding'], finding.get('revision'))
        if episode not in self._explanations:
            self._explanations[episode] = self.explainer(finding)
        return self._explanations[episode]

    # execute (single attempt) + verify --------------------------------------------------------------------
    def execute(self, request_id, token):
        with self._lock:
            self._expire()
            proposal = self.proposals.get(request_id)
            if proposal is None or proposal['state'] != 'proposed':
                proposal = None
        if proposal is None:
            # An unknown ID came from the caller: record it only if it has the shape of an ID this agent issues, so caller
            # text never reaches the audit log or the timeline the console shows.
            self.record('denied', None, code='UNKNOWN_OR_USED_REQUEST',
                        request_id=request_id if isinstance(request_id, str) and REQUEST_ID.fullmatch(request_id) else None)
            return {'result': 'DENIED', 'code': 'UNKNOWN_OR_USED_REQUEST'}
        key = proposal['target']
        try:
            claims = self.verifier.consume(token, proposal)
        except approval.ApprovalDenied as denied:
            self.record('denied', key, code=denied.code, request_id=request_id)
            return {'result': 'DENIED', 'code': denied.code}
        except Exception:
            self.record('denied', key, code='APPROVAL_STORAGE_UNAVAILABLE', request_id=request_id)
            return {'result': 'DENIED', 'code': 'APPROVAL_STORAGE_UNAVAILABLE'}
        # The token is consumed from here on: every outcome below leaves this request unusable.
        if self.executor is not None:
            proposal['state'] = 'delegated'
            try:
                result = self.executor.execute(proposal, token)
                if (set(result) != {'result', 'code'} or result['result'] not in ('VERIFIED', 'NOT_VERIFIED', 'DENIED', 'FAILED')
                        or type(result['code']) is not str or not re.fullmatch(r'[A-Z0-9_:]{1,100}', result['code'])):
                    raise ValueError('executor response')
            except Exception:
                result = {'result': 'NOT_VERIFIED', 'code': 'EXECUTOR_UNAVAILABLE'}
            proposal['state'] = 'verified' if result['result'] == 'VERIFIED' else 'not_verified'
            self.record('verified' if result['result'] == 'VERIFIED' else 'failed', key,
                        code=result['code'], request_id=request_id, authority='ops-executor')
            return result
        try:
            observed, pods, events = self.observe(key)
            fresh = diagnose.diagnose(observed, pods, events)  # fresh GET, never the cached scan
        except KubeError as error:
            proposal['state'] = 'failed'
            self.record('failed', key, code='OBSERVE_' + str(error.status), request_id=request_id)
            return {'result': 'FAILED', 'code': 'OBSERVE_' + str(error.status)}
        code = ('TARGET_REPLACED' if fresh['uid'] != proposal['uid']
                else 'EVIDENCE_CHANGED' if fresh['evidence_digest'] != proposal['evidence_digest']
                else 'OBJECT_CHANGED' if fresh['resource_version'] != proposal['resource_version'] else None)
        if code is not None:
            proposal['state'] = 'stale'
            self.record('denied', key, code=code, request_id=request_id)
            return {'result': 'DENIED', 'code': code}
        proposal['state'] = 'approved'
        self.record('approved', key, request_id=request_id, approver=claims['approver'])
        target = self.targets[key]
        try:
            patch = actions.plan(proposal['action'], target, proposal['arguments'])
            # Precondition: the API server applies the patch only to this exact object version, else 409. A same-name
            # replacement always has another resourceVersion (they are never reused), so it is refused the same way.
            patch['metadata'] = {'resourceVersion': proposal['resource_version']}
            expected_template = copy.deepcopy(observed['spec'].get('template', {}))
            if proposal['action'] == 'restart':
                expected_template.setdefault('metadata', {}).setdefault('annotations', {}).update(
                    patch['spec']['template']['metadata']['annotations'])
            expected_replicas = patch['spec'].get('replicas', observed['spec'].get('replicas', 1))
            self.client.patch_deployment(target.namespace, target.name, patch)  # exactly one attempt
        except actions.ActionRejected as rejected:
            proposal['state'] = 'failed'
            self.record('failed', key, code=rejected.code, request_id=request_id)
            return {'result': 'FAILED', 'code': rejected.code}
        except KubeError as error:
            if error.status == 409:  # the object changed after the fresh GET: nothing was applied
                proposal['state'] = 'stale'
                self.record('denied', key, code='CONFLICT_OBJECT_CHANGED', request_id=request_id)
                return {'result': 'DENIED', 'code': 'CONFLICT_OBJECT_CHANGED'}
            proposal['state'] = 'failed'
            code = 'ADMISSION_REJECTED' if error.status in (400, 403, 422) else 'API_' + str(error.status)
            self.record('denied' if code == 'ADMISSION_REJECTED' else 'failed', key, code=code, request_id=request_id)
            return {'result': 'FAILED', 'code': code}
        proposal['state'] = 'executed'
        self.record('executed', key, request_id=request_id, action=proposal['action'])
        try:
            outcome = actions.verify(self.client, target, expected_uid=proposal['uid'],
                                     expected_replicas=expected_replicas, expected_template=expected_template,
                                     **self._verify_kwargs)
        except Exception:
            outcome = {'verified': False, 'code': 'VERIFICATION_UNAVAILABLE'}
        proposal['state'] = 'verified' if outcome['verified'] else 'not_verified'
        self.record('verified' if outcome['verified'] else 'failed', key, request_id=request_id, code=outcome['code'])
        return {'result': 'VERIFIED' if outcome['verified'] else 'NOT_VERIFIED', 'code': outcome['code']}

    def posture(self):
        started_at = round(self.clock(), 3)
        workloads = {}
        for target in self.targets.values():
            workloads.setdefault(target.namespace, []).append(target.name)
        return dict(posture.check(self.client, sorted(workloads), workloads), checked_at=round(self.clock(), 3), started_at=started_at,
                    source='ops-agent /v1/posture', max_age_seconds=FRESH_SECONDS)

    def snapshot(self):
        with self._lock:
            self._expire()
            return {'timeline': list(self.timeline)[-50:], 'denials': list(self.denials)[-20:],
                    'pending': [p for p in self.proposals.values() if p['state'] == 'proposed'],
                    'findings': dict(self.findings)}

    ACTIVITY_SECONDS = 10

    def activity(self):
        """Masking/blocked events from the redactor's audit lines, cached so a polling console cannot multiply log reads."""
        with self._lock:
            cached = getattr(self, '_activity', None)
            if cached is not None and self.clock() - cached[0] < self.ACTIVITY_SECONDS:
                return cached[1]
        value = activity.recent(self.client)
        with self._lock:
            self._activity = (self.clock(), value)
        return value
