"""Deterministic diagnosis of a registered Deployment from Kubernetes state (no model involved).

Closed findings: CRASH_LOOP, OOM_KILLED, IMAGE_PULL, ADMISSION_DENIED, PENDING, READINESS_FAILING, HEALTHY.
Each finding carries evidence references (object kind/name/reason) and the actions that may help; logs are
never parsed for instructions, only counted/attached as untrusted, redacted context for an explanation.
"""
import hashlib
import json
import re

# Findings whose fix needs a Pod spec change (image, env, resources) get no proposal: that is an owner change,
# outside the agent's authority (no rollback; see policies/admission.yaml).
SUGGESTED = {'CRASH_LOOP': ('restart',), 'OOM_KILLED': (), 'IMAGE_PULL': (), 'ADMISSION_DENIED': (),
             'PENDING': ('scale',), 'READINESS_FAILING': ('restart',), 'HEALTHY': ()}
# The recommendation shown to the owner for those findings (closed codes; the UI localizes them).
OWNER_ACTION = {'OOM_KILLED': 'RAISE_MEMORY_LIMIT_OR_FIX_WORKLOAD', 'IMAGE_PULL': 'DEPLOY_VALID_SIGNED_DIGEST',
                'ADMISSION_DENIED': 'DEPLOY_ATTESTED_IMAGE'}


def _waiting(status):
    return ((status.get('state') or {}).get('waiting') or {}).get('reason')


def _last_terminated(status):
    return ((status.get('lastState') or {}).get('terminated') or {}).get('reason')


def live_pods(pods):
    """Pods that still belong to the workload: a Pod with a deletionTimestamp is terminating (for example the old Pod
    of a verified restart) and its readiness says nothing about the workload any more."""
    return [pod for pod in pods if not (pod.get('metadata') or {}).get('deletionTimestamp')]


def diagnose(deployment, pods, events, replicasets=()):
    name = deployment['metadata']['name']
    pods = live_pods(pods)
    findings, evidence = [], []
    for pod in pods:
        pod_name = pod['metadata']['name']
        phase = (pod.get('status') or {}).get('phase')
        statuses = (pod.get('status') or {}).get('containerStatuses') or []
        if phase == 'Pending' and not statuses:
            unschedulable = [c for c in (pod['status'].get('conditions') or [])
                             if c.get('type') == 'PodScheduled' and c.get('status') == 'False']
            if unschedulable:
                findings.append('PENDING'); evidence.append({'kind': 'Pod', 'name': pod_name, 'reason': unschedulable[0].get('reason', 'Unschedulable')})
        for status in statuses:
            waiting, last = _waiting(status), _last_terminated(status)
            if last == 'OOMKilled' or ((status.get('state') or {}).get('terminated') or {}).get('reason') == 'OOMKilled':
                findings.append('OOM_KILLED'); evidence.append({'kind': 'Pod', 'name': pod_name, 'reason': 'OOMKilled'})
            elif waiting == 'CrashLoopBackOff':
                findings.append('CRASH_LOOP'); evidence.append({'kind': 'Pod', 'name': pod_name, 'reason': 'CrashLoopBackOff',
                                                                'restarts': int(status.get('restartCount', 0))})
            elif waiting in ('ImagePullBackOff', 'ErrImagePull', 'InvalidImageName'):
                findings.append('IMAGE_PULL'); evidence.append({'kind': 'Pod', 'name': pod_name, 'reason': waiting})
            elif phase == 'Running' and not status.get('ready') and 'running' in (status.get('state') or {}):
                findings.append('READINESS_FAILING'); evidence.append({'kind': 'Pod', 'name': pod_name, 'reason': 'NotReady'})
    for event in events:
        involved = event.get('involvedObject') or {}
        message = str(event.get('message', ''))
        if (event.get('reason') == 'FailedCreate' and involved.get('kind') == 'ReplicaSet'
                and involved.get('name', '').startswith(name + '-')
                and ('image policy' in message.lower() or 'binary authorization' in message.lower() or 'denied the request' in message.lower())):
            findings.append('ADMISSION_DENIED'); evidence.append({'kind': 'ReplicaSet', 'name': involved['name'], 'reason': 'FailedCreate:admission'})
    status = deployment.get('status') or {}
    desired = int((deployment.get('spec') or {}).get('replicas', 1))
    if not findings and desired > 0 and int(status.get('availableReplicas', 0)) < desired and not pods:
        findings.append('PENDING'); evidence.append({'kind': 'Deployment', 'name': name, 'reason': 'NoPods'})
    order = ['ADMISSION_DENIED', 'IMAGE_PULL', 'OOM_KILLED', 'CRASH_LOOP', 'PENDING', 'READINESS_FAILING']
    primary = next((f for f in order if f in findings), 'HEALTHY')
    result = {'deployment': name, 'namespace': deployment['metadata']['namespace'], 'finding': primary,
              'all_findings': sorted(set(findings)), 'evidence': evidence[:10], 'suggested_actions': list(SUGGESTED[primary]),
              'observed_generation': status.get('observedGeneration'), 'desired_replicas': desired,
              'available_replicas': int(status.get('availableReplicas', 0)),
              'revision': (deployment['metadata'].get('annotations') or {}).get('deployment.kubernetes.io/revision'),
              'uid': deployment['metadata'].get('uid'), 'resource_version': deployment['metadata'].get('resourceVersion')}
    result['automated_fix'] = bool(SUGGESTED[primary])
    result['owner_action'] = OWNER_ACTION.get(primary)
    result['evidence_digest'] = hashlib.sha256(json.dumps(
        {k: result[k] for k in ('deployment', 'namespace', 'uid', 'finding', 'evidence', 'revision')}, sort_keys=True).encode()).hexdigest()
    return result


DIGEST = re.compile(r'sha256:[0-9a-f]{64}')


def live_facts(pods):
    """Console facts from the Pods already read for a scan: counts and running image digests only.

    The registry path in a Pod's imageID (which contains the project) is dropped: only the digest is kept."""
    ready, restarts, digests = 0, 0, set()
    for pod in pods:
        statuses = (pod.get('status') or {}).get('containerStatuses') or []
        if (pod.get('status') or {}).get('phase') == 'Running' and statuses and all(s.get('ready') for s in statuses):
            ready += 1
        for status in statuses:
            restarts += int(status.get('restartCount', 0))
            found = DIGEST.search(str(status.get('imageID', '')))
            if found:
                digests.add(found.group(0))
    return {'pods_total': len(pods), 'pods_ready': ready, 'restarts': restarts, 'image_digests': sorted(digests)}
