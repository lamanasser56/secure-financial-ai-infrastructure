"""Split the private disposable bundle without relaxing Fail/Deny admission.

The database must start before its schema Job; the redactor's durable counter
Job must complete before its Deployment. The schema Job waits for the gateway,
so it completes after stage 6 starts the gateway. Read both ledgers through the
redactor before the first case and before and after every case.
"""

import hashlib
import json
import os
from pathlib import Path

import yaml


POLICY = 'ops-agent-bounded-remediation'


def key(doc):
    meta = doc['metadata']
    return doc['kind'], meta.get('namespace', ''), meta['name']


def split(docs):
    keys = [key(doc) for doc in docs]
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate Kubernetes object')
    names = set(keys)
    required = {('ConfigMap', 'ops', 'ops-agent-registry'),
        ('ValidatingAdmissionPolicy', '', POLICY),
        ('ValidatingAdmissionPolicyBinding', '', POLICY),
        ('StatefulSet', 'platform', 'postgres'),
        ('Job', 'platform', 'assessment-sdp-seed'),
        ('Deployment', 'platform', 'redactor')}
    if not required <= names:
        raise ValueError('missing staged dependency: ' + str(required - names))
    stages = [[] for _ in range(7)]
    for doc in docs:
        kind, namespace, name = key(doc)
        if kind in ('Namespace', 'ServiceAccount', 'StorageClass'):
            stage = 0
        elif kind == 'ValidatingAdmissionPolicy':
            stage = 2
        elif kind == 'ValidatingAdmissionPolicyBinding':
            stage = 3
        elif kind == 'StatefulSet':
            stage = 4
        elif kind == 'Job':
            stage = 5
        elif kind == 'Deployment':
            stage = 6
        else:
            stage = 1
        stages[stage].append(doc)
    policy = next(d for d in stages[2] if key(d) == ('ValidatingAdmissionPolicy', '', POLICY))
    binding = next(d for d in stages[3] if key(d) == ('ValidatingAdmissionPolicyBinding', '', POLICY))
    if (policy['spec'].get('failurePolicy') != 'Fail'
            or binding['spec'].get('validationActions') != ['Deny', 'Audit']
            or binding['spec']['paramRef'] != {'name': 'ops-agent-registry',
                'namespace': 'ops', 'parameterNotFoundAction': 'Deny'}):
        raise ValueError('Ops policy no longer fails closed')
    if set().union(*(set(map(key, stage)) for stage in stages)) != names:
        raise ValueError('staging lost an object')
    return stages


def write(stages, directory):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = []
    for i, stage in enumerate(stages):
        path = directory / ('stage-%d.yaml' % i)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            stream.write(yaml.safe_dump_all(stage, sort_keys=False))
        result.append({'stage': i, 'objects': len(stage),
                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('private_bundle', type=Path)
    parser.add_argument('private_stage_directory', type=Path)
    args = parser.parse_args()
    docs = [d for d in yaml.safe_load_all(args.private_bundle.read_text()) if d]
    print(json.dumps(write(split(docs), args.private_stage_directory), sort_keys=True))
