"""Allowlisted remediation: rollout restart and bounded scale. There is no rollback: the agent never changes a
Pod spec (see policies/admission.yaml).

Each action is one merge-PATCH of a registered Deployment (never retried), followed by verification:
rollout complete (observedGeneration, updated == available == desired) and, when registered, a health URL
returning 200, within a bound. The admission policy rejects anything else server-side.
"""
from datetime import datetime, timezone
import time
import urllib.request

RESTART_ANNOTATION = 'kubectl.kubernetes.io/restartedAt'


class ActionRejected(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def plan(action, target, arguments, now=None):
    """Return the exact patch for an approved proposal (pure; tested offline)."""
    if action == 'restart':
        if arguments:
            raise ActionRejected('ARGUMENTS')
        stamp = (now or datetime.now(timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')
        return {'spec': {'template': {'metadata': {'annotations': {RESTART_ANNOTATION: stamp}}}}}
    if action == 'scale':
        if set(arguments) != {'replicas'} or type(arguments['replicas']) is not int:
            raise ActionRejected('ARGUMENTS')
        if not target.min_replicas <= arguments['replicas'] <= target.max_replicas:
            raise ActionRejected('SCALE_OUT_OF_BOUNDS')
        return {'spec': {'replicas': arguments['replicas']}}
    raise ActionRejected('ACTION_NOT_ALLOWLISTED')


def rollout_complete(deployment):
    status, spec, meta = deployment.get('status') or {}, deployment['spec'], deployment['metadata']
    desired = int(spec.get('replicas', 1))
    return (int(status.get('observedGeneration', 0)) >= int(meta.get('generation', 0))
            and int(status.get('updatedReplicas', 0)) == desired and int(status.get('availableReplicas', 0)) == desired
            and int(status.get('replicas', 0)) == desired and not status.get('unavailableReplicas'))


def health_ok(url, opener=None, timeout=5):
    if url is None:
        return True
    try:
        with (opener or urllib.request.build_opener(urllib.request.ProxyHandler({})).open)(url, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def verify(client, target, *, expected_uid, expected_replicas, expected_template,
           timeout=180, interval=5, sleep=time.sleep, clock=time.monotonic, opener=None):
    deadline = clock() + timeout
    while clock() < deadline:
        current = client.get('deployments', target.namespace, target.name)
        if current['metadata']['uid'] != expected_uid:
            return {'verified': False, 'code': 'TARGET_REPLACED_DURING_VERIFICATION'}
        if (current['spec'].get('replicas', 1) != expected_replicas
                or current['spec'].get('template', {}) != expected_template):
            return {'verified': False, 'code': 'DESIRED_STATE_CHANGED_DURING_VERIFICATION'}
        if rollout_complete(current) and health_ok(target.health, opener=opener):
            return {'verified': True, 'code': 'ROLLOUT_COMPLETE_AND_HEALTHY', 'available_replicas': current['status'].get('availableReplicas', 0)}
        sleep(interval)
    return {'verified': False, 'code': 'VERIFICATION_TIMEOUT'}
