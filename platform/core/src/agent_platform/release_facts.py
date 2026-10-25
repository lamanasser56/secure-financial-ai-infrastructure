"""Sanitized declarations from one selected render. Observations still come from Ops, never from this file."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import yaml

from agent_platform.release_version import source_commit

NAME = 'console-release-facts'
MOUNT = Path('/release/console.json')
KINDS = {'Namespace', 'Deployment', 'StatefulSet', 'NetworkPolicy', 'FQDNNetworkPolicy', 'ConfigMap'}
FIELDS = {'schema_version', 'source_commit', 'agents', 'documents', 'model', 'bound_to_release'}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def extract(docs, manifests, *, commit=None, private_values=(), bound=True):
    """Closed projection: no Secrets, executable ConfigMaps, identity annotations, env, or registry paths."""
    out, model = [], None
    for doc in docs:
        kind = doc.get('kind')
        if kind not in KINDS:
            continue
        metadata = {k: doc['metadata'][k] for k in ('name', 'namespace') if k in doc['metadata']}
        item = {'kind': kind, 'metadata': metadata}
        if kind == 'Namespace':
            item['metadata']['labels'] = {k: v for k, v in doc['metadata'].get('labels', {}).items()
                                          if k.startswith('pod-security.kubernetes.io/')}
        elif kind in ('Deployment', 'StatefulSet'):
            pod = doc['spec']['template']['spec']
            containers = []
            for container in pod.get('containers', []):
                image = container.get('image', '')
                digest = image.rsplit('@', 1)[-1] if '@' in image else None
                containers.append({k: deepcopy(container[k]) for k in ('name', 'command', 'ports') if k in container})
                containers[-1]['image'] = digest if re.fullmatch(r'sha256:[0-9a-f]{64}', digest or '') else 'unbuilt'
            item['spec'] = {'replicas': doc['spec'].get('replicas', 1),
                            'template': {'spec': {'containers': containers}}}
        elif kind in ('NetworkPolicy', 'FQDNNetworkPolicy'):
            item['spec'] = deepcopy(doc['spec'])
        elif metadata['name'] in ('ops-agent-registry', 'ops-agent-observe'):
            item['data'] = deepcopy(doc['data'])
        else:
            if metadata['name'].startswith('gateway-config-') and 'litellm.yaml' in doc.get('data', {}):
                config = yaml.safe_load(doc['data']['litellm.yaml'])
                entries = config.get('model_list') or []
                if entries:
                    model = str(entries[0].get('litellm_params', {}).get('model', '')).rpartition('/')[2] or None
            continue
        out.append(item)
    agents = {}
    for name, manifest in sorted(manifests.items()):
        agents[name] = {k: deepcopy(manifest[k]) for k in
                        ('agent', 'team', 'description', 'runtime', 'model', 'redaction', 'tools', 'data')}
    value = {'schema_version': 1, 'source_commit': source_commit(commit), 'agents': agents,
             'documents': sorted(out, key=lambda d: (d['kind'], d['metadata'].get('namespace', ''), d['metadata']['name'])),
             'model': model, 'bound_to_release': bool(bound)}

    def scrub(value):
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, str):
            for private in private_values:
                if private:
                    value = value.replace(private, '[withheld]')
            value = re.sub(r'\b\d{10,13}\b', '[withheld]', value)
        return value
    return scrub(value)


def validate(value):
    if not isinstance(value, dict) or set(value) != FIELDS or value['schema_version'] != 1:
        raise ValueError('release facts shape')
    if value['source_commit'] is not None and source_commit(value['source_commit']) is None:
        raise ValueError('release source version')
    if type(value['bound_to_release']) is not bool or not isinstance(value['agents'], dict) or not isinstance(value['documents'], list):
        raise ValueError('release facts types')
    for doc in value['documents']:
        if doc.get('kind') not in KINDS or not isinstance(doc.get('metadata'), dict):
            raise ValueError('release declaration kind')
        if set(doc) - {'kind', 'metadata', 'spec', 'data'}:
            raise ValueError('release declaration fields')
    if len(encode(value).encode()) > 512_000:
        raise ValueError('release facts size')
    return value


def load(path=MOUNT):
    return validate(json.loads(Path(path).read_text()))


def verify(docs):
    configs = [d for d in docs if d['kind'] == 'ConfigMap' and d['metadata'].get('namespace') == 'apps'
               and d['metadata']['name'].startswith(NAME)]
    if len(configs) != 1:
        raise ValueError('one release facts ConfigMap required')
    config = configs[0]
    facts = validate(json.loads(config['data']['console.json']))
    expected = extract(docs, facts['agents'], commit=facts['source_commit'])
    raw = encode(facts)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    if facts != expected or config['metadata']['name'] != NAME + '-' + digest[:12]:
        raise ValueError('release facts do not match selected manifests')
    app = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata'].get('namespace') == 'apps'
               and d['metadata']['name'] == 'app')
    template = app['spec']['template']
    volume = next(v for v in template['spec']['volumes'] if v['name'] == 'release-facts')
    mount = next(m for c in template['spec']['containers'] if c['name'] == 'app'
                 for m in c['volumeMounts'] if m['name'] == 'release-facts')
    if (volume['configMap']['name'] != config['metadata']['name']
            or mount != {'name': 'release-facts', 'mountPath': '/release', 'readOnly': True}
            or template['metadata'].get('annotations', {}).get('platform.example/release-facts-sha256') != digest):
        raise ValueError('release facts mount or rollout version differs')
    return facts


def install(docs, manifests, lock, *, private_values=()):
    """Content-address the projection and its mount. Excluded generated fields avoid a hash cycle."""
    facts = validate(extract(docs, manifests, commit=lock.get('source_commit'), private_values=private_values))
    raw = encode(facts)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    config = next(d for d in docs if d['kind'] == 'ConfigMap' and d['metadata'].get('namespace') == 'apps'
                  and d['metadata']['name'].startswith(NAME))
    config['metadata']['name'] = NAME + '-' + digest[:12]
    config['data'] = {'console.json': raw}
    app = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata'].get('namespace') == 'apps'
               and d['metadata']['name'] == 'app')
    template = app['spec']['template']
    template['metadata'].setdefault('annotations', {})['platform.example/release-facts-sha256'] = digest
    volume = next(v for v in template['spec']['volumes'] if v['name'] == 'release-facts')
    volume['configMap']['name'] = config['metadata']['name']
    if facts['source_commit']:
        for doc in docs:
            if doc['kind'] not in ('Deployment', 'StatefulSet'):
                continue
            for container in doc['spec']['template']['spec'].get('containers', []):
                env = container.setdefault('env', [])
                env[:] = [e for e in env if e['name'] != 'PLATFORM_SOURCE_COMMIT']
                env.append({'name': 'PLATFORM_SOURCE_COMMIT', 'value': facts['source_commit']})
    return facts


def repository(root=None):
    """Explicit development mode: the actual current Kustomize composition, marked unbound to a release."""
    root = Path(root) if root else Path(__file__).resolve().parents[4]
    kubectl = shutil.which('kubectl') or str(root / '.cache/envtest-v1.35.0/kubectl')
    result = subprocess.run([kubectl, 'kustomize', '--load-restrictor', 'LoadRestrictionsNone',
                             str(root / 'platform/clouds/gke/kubernetes')], capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError('source manifest composition unavailable')
    manifests = {p.parent.name: yaml.safe_load(p.read_text()) for p in (root / 'platform/agents').glob('*/agent.yaml')}
    return validate(extract([d for d in yaml.safe_load_all(result.stdout) if d], manifests, bound=False))
