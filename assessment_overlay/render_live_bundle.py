"""Render a disposable assessment bundle from unmodified main platform source.

This is a pure file transform. It never contacts Kubernetes or GCP and never
generates or stores credentials. The caller supplies a fresh run ID and keeps
the generated file outside the repository's tracked source.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from types import SimpleNamespace

import yaml

from patch_gateway_stub import patch as patch_gateway
from patch_ops_stub import patch as patch_ops
from patch_redactor_bundle import patch as patch_redactor


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = Path(__file__).resolve().parent
PROJECT = 'sfai-assess-20261022-635651'
IMAGE_LOCK = OVERLAY / 'platform-images.lock.json'


def identity(doc):
    meta = doc['metadata']
    return doc['kind'], meta.get('namespace', ''), meta['name']


def exact_one(docs, kind, namespace, name):
    found = [d for d in docs if identity(d) == (kind, namespace, name)]
    if len(found) != 1:
        raise ValueError('missing/duplicate exact object: ' + str((kind, namespace, name)))
    return found[0]


def disposable_changes(docs, run_id):
    """Only assessment cluster plumbing; no platform program or image edits."""
    if not re.fullmatch(r'assess-[0-9a-f]{16}', run_id):
        raise ValueError('fresh assessment run ID required')
    docs = list(docs)
    for doc in docs:
        if doc['kind'] == 'Namespace':
            doc['metadata'].setdefault('labels', {})['assessment.run'] = run_id
        if (doc['kind'] == 'NetworkPolicy' and doc['metadata'].get('name') == 'allow-dns'
                and doc['metadata'].get('namespace') in
                ('platform', 'apps', 'ops', 'agent-financial', 'agent-platform-guide')):
            egress = doc['spec']['egress']  # main ships the node-local-dns peer the live run needed
            if (len(egress) != 1 or egress[0]['to'] != [
                    {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                     'podSelector': {'matchLabels': {'k8s-app': app}}} for app in ('kube-dns', 'node-local-dns')]):
                raise ValueError('DNS policy drift')
    retained = exact_one(docs, 'StorageClass', '', 'agent-platform-retain')
    disposable = exact_one(docs, 'StorageClass', '', 'agent-runtime-disposable')
    if disposable['reclaimPolicy'] != 'Delete' or retained['reclaimPolicy'] != 'Retain':
        raise ValueError('storage reclaim policy drift')
    docs.remove(retained)
    database = exact_one(docs, 'StatefulSet', 'platform', 'postgres')
    claim = database['spec']['volumeClaimTemplates'][0]['spec']
    if claim['storageClassName'] != 'agent-platform-retain':
        raise ValueError('database storage class drift')
    claim['storageClassName'] = 'agent-runtime-disposable'
    for name in ('assess-harness', 'assess-restore'):
        docs.extend((
            {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': name,
                'labels': {'pod-security.kubernetes.io/enforce': 'restricted',
                           'assessment.run': run_id}}},
            {'apiVersion': 'v1', 'kind': 'ResourceQuota',
             'metadata': {'name': 'assessment-quota', 'namespace': name},
             'spec': {'hard': {'pods': '3', 'services.loadbalancers': '0',
                 'services.nodeports': '0', 'requests.cpu': '500m',
                 'requests.memory': '512Mi', 'limits.cpu': '1000m',
                 'limits.memory': '1Gi'}}},
            {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
             'metadata': {'name': 'default-deny', 'namespace': name},
             'spec': {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress']}},
        ))
    return docs


def make_bundle(run_id, kubectl='kubectl', *, passphrase=None, hasher=None,
                users_out=None, source_registry=None):
    lock = json.loads(IMAGE_LOCK.read_text())
    if lock['source_commit'] != '41ffbf260a446b5db2292356a8ea23219e58a524':
        raise ValueError('platform source lock drift')
    module_path = ROOT / 'platform/clouds/gke/render.py'
    spec = importlib.util.spec_from_file_location('_assessment_main_gke_render', module_path)
    main_render = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_render)
    registry = source_registry or lock['registry']
    if (not registry.startswith('us-east1-docker.pkg.dev/')
            or not registry.endswith('/sdp-evaluation-images/')):
        raise ValueError('source registry must be the reviewed image repository')
    effective_lock = dict(lock, registry=registry)
    with tempfile.TemporaryDirectory(prefix='assessment-image-lock-') as temporary:
        private_lock = Path(temporary) / 'images.json'
        with os.fdopen(os.open(private_lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            json.dump(effective_lock, stream)
        args = SimpleNamespace(project_id=PROJECT, images_lock=str(private_lock),
            control_plane_cidr='172.30.0.0/28',
            gateway_gsa=f'assess-gateway@{PROJECT}.iam.gserviceaccount.com',
            redactor_gsa=f'assess-redactor@{PROJECT}.iam.gserviceaccount.com',
            kubectl=kubectl)
        source_text, main_summary = main_render.render(args)
    if main_summary['objects'] != 113:
        raise ValueError('main object count drift')
    docs = [doc for doc in yaml.safe_load_all(source_text) if doc]
    if not passphrase:
        raise ValueError('assessment operator passphrase required')
    from agent_platform import platform_secrets
    secret_options = {'users_out': users_out}
    if hasher is not None:
        secret_options['hasher'] = hasher
    secret_docs = platform_secrets.generate(passphrase, **secret_options)
    docs.extend(secret_docs)
    platform_programs = next(d for d in docs if d['kind'] == 'ConfigMap'
                             and d['metadata']['name'].startswith('platform-programs-'))
    program_hash = hashlib.sha256(json.dumps(platform_programs['data'], sort_keys=True).encode()).hexdigest()
    docs, gateway_receipt = patch_gateway(docs, registry + lock['images']['app'])
    docs, seed_objects, redactor_deployment = patch_redactor(docs, OVERLAY, run_id)
    docs = patch_ops(docs, OVERLAY / 'ops_server_assessment.py')
    docs = disposable_changes(docs, run_id)
    patched_programs = next(d for d in docs if d['kind'] == 'ConfigMap'
                            and d['metadata']['name'].startswith('platform-programs-'))
    if hashlib.sha256(json.dumps(patched_programs['data'], sort_keys=True).encode()).hexdigest() != program_hash:
        raise ValueError('platform program bytes changed')
    keys = [identity(doc) for doc in docs]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate Kubernetes object')
    route = next(d for d in docs if d['kind'] == 'ConfigMap'
                 and d['metadata']['name'].startswith('gateway-config-'))
    if 'vertex_ai/' in json.dumps(docs) or 'vertex_ai/' in route['data']['litellm.yaml']:
        raise ValueError('external LLM route retained')
    if 'PORTFOLIO_' + PROJECT in json.dumps(docs):
        raise ValueError('rendered environment corruption retained')
    if any(d['kind'] == 'FQDNNetworkPolicy' and d['metadata']['name'] == 'gateway-provider'
           for d in docs):
        raise ValueError('external gateway egress retained')
    receipt = {'run_id': run_id, 'platform_commit': lock['source_commit'],
        'main_render_sha256': hashlib.sha256(source_text.encode()).hexdigest(),
        'platform_programs_sha256': program_hash,
        'objects': len(docs), 'gateway': gateway_receipt,
        'seed_objects': [identity(d) for d in seed_objects],
        'redactor_deployment': identity(redactor_deployment),
        'image_digests': lock['images'], 'external_llm_route': False}
    receipt['source_registry'] = registry
    return docs, receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kubectl', default='kubectl')
    args = parser.parse_args()
    source_registry = os.environ.get('ASSESSMENT_SOURCE_REGISTRY')
    if not source_registry or source_registry == json.loads(IMAGE_LOCK.read_text())['registry']:
        raise SystemExit('exact source registry required in ASSESSMENT_SOURCE_REGISTRY')
    output = args.output.resolve()
    if output.is_relative_to(ROOT.resolve()):
        raise SystemExit('assessment manifest contains credentials; output outside repository required')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(args.output.parent, 0o700)
    passphrase = secrets.token_urlsafe(32)
    users = {}
    docs, receipt = make_bundle(args.run_id, args.kubectl, passphrase=passphrase,
                                users_out=users, source_registry=source_registry)
    for name, value in (('operator-passphrase', passphrase),
                        ('financial-users.json', json.dumps(users, sort_keys=True))):
        path = output.parent / name
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            stream.write(value + '\n')
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        stream.write(yaml.safe_dump_all(docs, sort_keys=False))
    receipt['bundle_sha256'] = hashlib.sha256(args.output.read_bytes()).hexdigest()
    with os.fdopen(os.open(output.with_suffix('.lock.json'),
                           os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
