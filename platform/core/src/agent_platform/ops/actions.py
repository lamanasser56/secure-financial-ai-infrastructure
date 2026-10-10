"""Allowlisted remediation: rollout restart, rollback to the previous revision, bounded scale.

Each action is one merge-PATCH of a registered Deployment (never retried), followed by verification:
rollout complete (observedGeneration, updated == available == desired) and, when registered, a health URL
returning 200, within a bound. The admission policy rejects anything else server-side.
"""
from datetime import datetime, timezone
import copy
import time
import urllib.request

RESTART_ANNOTATION = 'kubectl.kubernetes.io/restartedAt'
TEMPLATE_HASH_LABEL = 'pod-template-hash'


class ActionRejected(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def merge_patch(old, new):
    """RFC 7396 patch that turns `old` into exactly `new` (removed keys become null; lists are replaced)."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return copy.deepcopy(new)
    patch = {}
    for key in old.keys() - new.keys():
        patch[key] = None
    for key, value in new.items():
        if key not in old:
            patch[key] = copy.deepcopy(value)
        elif old[key] != value:
            patch[key] = merge_patch(old[key], value) if isinstance(value, dict) and isinstance(old[key], dict) else copy.deepcopy(value)
    return patch


def strip_template(template):
    template = copy.deepcopy(template)
    labels = template.get('metadata', {}).get('labels') or {}
    labels.pop(TEMPLATE_HASH_LABEL, None)
    return template


def previous_template(deployment, replicasets):
    """Template of the highest revision below the current one, owned by this Deployment."""
    uid = deployment['metadata']['uid']
    current = int((deployment['metadata'].get('annotations') or {}).get('deployment.kubernetes.io/revision', '0'))
    owned = []
    for rs in replicasets:
        owners = rs['metadata'].get('ownerReferences') or []
        revision = int((rs['metadata'].get('annotations') or {}).get('deployment.kubernetes.io/revision', '0'))
        if any(o.get('uid') == uid and o.get('kind') == 'Deployment' for o in owners) and 0 < revision < current:
            owned.append((revision, rs))
    if not owned:
        raise ActionRejected('NO_PREVIOUS_REVISION')
    return max(owned, key=lambda item: item[0])[1]['spec']['template']


def plan(action, target, deployment, replicasets, arguments, now=None):
    """Return the exact patch for an approved proposal (pure; tested offline)."""
    spec = deployment['spec']
    if action == 'restart':
        if arguments:
            raise ActionRejected('ARGUMENTS')
        stamp = (now or datetime.now(timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')
        return {'spec': {'template': {'metadata': {'annotations': {RESTART_ANNOTATION: stamp}}}}}, None
    if action == 'scale':
        if set(arguments) != {'replicas'} or type(arguments['replicas']) is not int:
            raise ActionRejected('ARGUMENTS')
        if not target.min_replicas <= arguments['replicas'] <= target.max_replicas:
            raise ActionRejected('SCALE_OUT_OF_BOUNDS')
        return {'spec': {'replicas': arguments['replicas']}}, None
    if action == 'rollback':
        if arguments:
            raise ActionRejected('ARGUMENTS')
        wanted = strip_template(previous_template(deployment, replicasets))
        images = [c['image'] for c in wanted['spec']['containers']]
        if not all(image in target.images for image in images):
            raise ActionRejected('ROLLBACK_IMAGE_NOT_REGISTERED')
        return {'spec': {'template': merge_patch(spec['template'], wanted)}}, wanted
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


def verify(client, target, expected_template=None, *, timeout=180, interval=5, sleep=time.sleep, clock=time.monotonic, opener=None):
    deadline = clock() + timeout
    while clock() < deadline:
        current = client.get('deployments', target.namespace, target.name)
        if expected_template is not None and strip_template(current['spec']['template']) != expected_template:
            return {'verified': False, 'code': 'TEMPLATE_NOT_EXACT_PREVIOUS_REVISION'}
        if rollout_complete(current) and health_ok(target.health, opener=opener):
            return {'verified': True, 'code': 'ROLLOUT_COMPLETE_AND_HEALTHY', 'available_replicas': current['status'].get('availableReplicas', 0)}
        sleep(interval)
    return {'verified': False, 'code': 'VERIFICATION_TIMEOUT'}
