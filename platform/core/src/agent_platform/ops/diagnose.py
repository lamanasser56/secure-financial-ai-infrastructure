"""Deterministic diagnosis of a registered Deployment from Kubernetes state (no model involved).

Closed findings: CRASH_LOOP, OOM_KILLED, IMAGE_PULL, ADMISSION_DENIED, PENDING, READINESS_FAILING, HEALTHY.
Each finding carries evidence references (object kind/name/reason) and the actions that may help; logs are
never parsed for instructions, only counted/attached as untrusted, redacted context for an explanation.
"""
import hashlib
import json

SUGGESTED = {'CRASH_LOOP': ('rollback', 'restart'), 'OOM_KILLED': ('rollback',), 'IMAGE_PULL': ('rollback',),
             'ADMISSION_DENIED': ('rollback',), 'PENDING': ('scale',), 'READINESS_FAILING': ('restart', 'rollback'),
             'HEALTHY': ()}


def _waiting(status):
    return ((status.get('state') or {}).get('waiting') or {}).get('reason')


def _last_terminated(status):
    return ((status.get('lastState') or {}).get('terminated') or {}).get('reason')


def diagnose(deployment, pods, events, replicasets=()):
    name = deployment['metadata']['name']
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
              'revision': (deployment['metadata'].get('annotations') or {}).get('deployment.kubernetes.io/revision')}
    result['evidence_digest'] = hashlib.sha256(json.dumps(
        {k: result[k] for k in ('deployment', 'namespace', 'finding', 'evidence', 'revision')}, sort_keys=True).encode()).hexdigest()
    return result
