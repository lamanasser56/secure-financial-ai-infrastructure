"""Assessment-only manifest transform: Ops explains with a fixed local stub.

The transformed Secret removes the Ops gateway and redactor credentials. The
signed Ops image is unchanged; a separately hashed, read-only ConfigMap
supplies its assessment entrypoint. This transform is restricted to one named
Deployment and one named Secret in the disposable bundle.
"""

import base64
import json
from pathlib import Path


OPS = {'namespace': 'ops', 'name': 'ops-agent'}


def patch(docs, launcher_path):
    docs = list(docs)
    deployments = [d for d in docs if d.get('kind') == 'Deployment' and
                   d.get('metadata', {}).get('namespace') == 'ops' and
                   d.get('metadata', {}).get('name') == 'ops-agent']
    secrets = [d for d in docs if d.get('kind') == 'Secret' and
               d.get('metadata', {}).get('namespace') == 'ops' and
               d.get('metadata', {}).get('name') == 'ops-agent']
    if len(deployments) != 1 or len(secrets) != 1:
        raise ValueError('exact Ops deployment and Secret required')
    deployment, secret = deployments[0], secrets[0]
    if 'data' in secret and 'stringData' in secret:
        raise ValueError('ambiguous Ops Secret')
    encoded = 'data' in secret
    field = 'data' if encoded else 'stringData'
    if set(secret.get(field, {})) != {'ops.json'}:
        raise ValueError('unexpected Ops Secret keys')
    raw = base64.b64decode(secret[field]['ops.json'], validate=True).decode() if encoded else secret[field]['ops.json']
    config = json.loads(raw)
    if (set(config) != {'api_key', 'approver_public_key', 'gateway_key', 'redactor_key', 'executor_key'}
            or not config['gateway_key'] or not config['redactor_key']):
        raise ValueError('unexpected Ops explanation credentials')
    config['gateway_key'] = config['redactor_key'] = ''
    updated = json.dumps(config, sort_keys=True, separators=(',', ':'))
    secret[field]['ops.json'] = base64.b64encode(updated.encode()).decode() if encoded else updated

    pod = deployment['spec']['template']['spec']
    containers = [c for c in pod['containers'] if c['name'] == 'ops-agent']
    if len(containers) != 1 or containers[0].get('command') != [
            '/usr/local/bin/python3.12', '-m', 'agent_platform.ops.server']:
        raise ValueError('unexpected Ops entrypoint')
    container = containers[0]
    if any(v['name'] == 'assessment-ops-stub' for v in pod.get('volumes', [])):
        raise ValueError('Ops stub already mounted')
    container['command'] = ['/usr/local/bin/python3.12', '/assessment/ops_server_assessment.py']
    container.setdefault('volumeMounts', []).append({
        'name': 'assessment-ops-stub', 'mountPath': '/assessment', 'readOnly': True})
    pod.setdefault('volumes', []).append({
        'name': 'assessment-ops-stub',
        'configMap': {'name': 'assessment-ops-stub', 'defaultMode': 292}})
    script = Path(launcher_path).read_text()
    configmap = {'apiVersion': 'v1', 'kind': 'ConfigMap',
                 'metadata': {'name': 'assessment-ops-stub', 'namespace': 'ops'},
                 'data': {'ops_server_assessment.py': script}}
    docs.insert(docs.index(deployment), configmap)
    return docs


def assert_order(docs):
    def position(kind, namespace, name):
        hits = [i for i, d in enumerate(docs) if d.get('kind') == kind and
                d.get('metadata', {}).get('namespace', '') == namespace and
                d.get('metadata', {}).get('name') == name]
        if len(hits) != 1:
            raise ValueError('missing or duplicate ordered dependency')
        return hits[0]

    if not (position('ConfigMap', 'ops', 'ops-agent-registry') <
            position('ValidatingAdmissionPolicyBinding', '', 'ops-agent-bounded-remediation')):
        raise ValueError('Ops registry must precede Fail/Deny binding')
    if not (position('ConfigMap', 'ops', 'assessment-ops-stub') <
            position('Deployment', 'ops', 'ops-agent')):
        raise ValueError('Ops assessment stub must precede Deployment')
