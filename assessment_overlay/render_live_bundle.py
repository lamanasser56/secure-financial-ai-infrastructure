"""Render a disposable assessment bundle from a selected current release lock.

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
import subprocess
import tempfile
from types import SimpleNamespace

import yaml

from patch_gateway_stub import patch as patch_gateway
from patch_ops_stub import patch as patch_ops
from patch_redactor_bundle import patch as patch_redactor


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = Path(__file__).resolve().parent


HARNESS = 'assessment_overlay/'
RELEASE_LOCK = 'platform/clouds/gke/release-rc1.lock.json'


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout


def checkout_changes(root=ROOT):
    """Paths that differ from HEAD: staged, unstaged, untracked, or hidden from status."""
    changed = set(git(root, 'diff', '--name-only', '--no-renames', 'HEAD').splitlines())
    # Only the repository's own .gitignore files may hide a file, not a personal exclude.
    changed |= set(git(root, 'ls-files', '--others', '--exclude-per-directory=.gitignore').splitlines())
    # assume-unchanged (lower-case tag) and skip-worktree (S) entries hide local edits.
    changed |= {line[2:] for line in git(root, 'ls-files', '-v').splitlines()
                if line[:1].islower() or line[:1] == 'S'}
    return sorted(changed)


def assessed_path(path):
    """Paths that may differ from S: the instrument, its release lock and evidence."""
    return path == RELEASE_LOCK or path.startswith('docs/evidence/') or path.startswith(HARNESS)


def selected_source(lock, root=ROOT):
    """Return S when this checkout runs S's product exactly.

    Everything outside assessment_overlay/ must equal S, except the release lock
    and docs/evidence/. The harness may change after S, but only in commits: an
    uncommitted or untracked change anywhere refuses the session, so a local
    edit can never pass as the committed harness or as S.
    """
    source = lock.get('source_commit')
    if (lock.get('schema_version') != 2 or lock.get('runtime_contract') != 'trusted-boundaries-v2'
            or not isinstance(source, str) or not re.fullmatch(r'[0-9a-f]{40}', source)):
        raise ValueError('current qualified image lock required')
    exists = subprocess.run(['git', 'cat-file', '-e', source + '^{commit}'], cwd=root,
                            capture_output=True, check=False)
    if exists.returncode:
        raise ValueError('selected source commit unavailable')
    if checkout_changes(root):
        raise ValueError('assessment checkout has uncommitted or untracked changes')
    # --no-renames lists both sides, so moving product code into the harness is refused.
    changed = git(root, 'diff', '--name-only', '--no-renames', source, 'HEAD').splitlines()
    if any(not assessed_path(path) for path in changed):
        raise ValueError('assessment source differs from qualified release')
    return source


def harness_record(source, root=ROOT):
    """The committed harness that runs against S, and its S..HEAD diff."""
    diff = git(root, 'diff', '--no-renames', '--binary', source, 'HEAD', '--', HARNESS)
    return {
        'harness_commit': git(root, 'rev-parse', 'HEAD').strip(),
        'harness_changed_files': git(root, 'diff', '--name-only', '--no-renames', source, 'HEAD',
                                     '--', HARNESS).splitlines(),
        'harness_diff_sha256': hashlib.sha256(diff.encode()).hexdigest(),
    }, diff


def assert_harness_unchanged(manifest, root=ROOT):
    """Each operator step runs the exact clean harness commit the session recorded."""
    if (git(root, 'rev-parse', 'HEAD').strip() != manifest.get('harness_commit')
            or checkout_changes(root)):
        raise SystemExit('assessment:harness_checkout_changed_since_session')


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
    # The assessed gateway has a private fixed provider only; do not grant it
    # the production Vertex Workload Identity in this disposable project.
    gateway_sa = exact_one(docs, 'ServiceAccount', 'platform', 'gateway')
    annotations = gateway_sa['metadata'].get('annotations', {})
    if set(annotations) != {'iam.gke.io/gcp-service-account'}:
        raise ValueError('gateway Workload Identity drift')
    del gateway_sa['metadata']['annotations']
    metadata_policy = exact_one(docs, 'NetworkPolicy', 'platform', 'workload-identity-metadata')
    expressions = metadata_policy['spec']['podSelector']['matchExpressions']
    if expressions != [{'key': 'app.kubernetes.io/name', 'operator': 'In',
                        'values': ['gateway', 'redactor']}]:
        raise ValueError('metadata egress policy drift')
    expressions[0]['values'] = ['redactor']
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


def make_bundle(run_id, kubectl='kubectl', *, project, images_lock, passphrase=None, hasher=None,
                users_out=None, runtime_registry=None):
    if not re.fullmatch(r'sfai-assess-[a-z0-9-]{6,32}', project or ''):
        raise ValueError('fresh disposable assessment project required')
    lock = json.loads(Path(images_lock).read_text())
    selected_source(lock)
    if not lock['images']['redactor'].startswith('agent-platform-redactor@sha256:'):
        raise ValueError('image-owned redactor required')
    module_path = ROOT / 'platform/clouds/gke/render.py'
    spec = importlib.util.spec_from_file_location('_assessment_main_gke_render', module_path)
    main_render = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_render)
    registry = runtime_registry
    if registry != f'us-east1-docker.pkg.dev/{project}/sdp-evaluation-images/':
        raise ValueError('runtime registry must belong to the disposable project')
    effective_lock = dict(lock, registry=registry)
    with tempfile.TemporaryDirectory(prefix='assessment-image-lock-') as temporary:
        private_lock = Path(temporary) / 'images.json'
        with os.fdopen(os.open(private_lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            json.dump(effective_lock, stream)
        args = SimpleNamespace(project_id=project, images_lock=str(private_lock),
            control_plane_cidr='172.16.0.16/28',
            gateway_gsa=f'agent-platform-gateway@{project}.iam.gserviceaccount.com',
            redactor_gsa=f'google-sdp-runtime@{project}.iam.gserviceaccount.com',
            kubectl=kubectl)
        source_text, main_summary = main_render.render(args)
    docs = [doc for doc in yaml.safe_load_all(source_text) if doc]
    if not passphrase:
        raise ValueError('assessment operator passphrase required')
    from agent_platform import platform_secrets
    secret_options = {'users_out': users_out}
    if hasher is not None:
        secret_options['hasher'] = hasher
    secret_docs = platform_secrets.generate(passphrase, **secret_options)
    docs.extend(secret_docs)
    if any(d['kind'] == 'ConfigMap' and d['metadata'].get('namespace') == 'platform'
           and d['metadata']['name'].startswith('platform-programs-') for d in docs):
        raise ValueError('executable platform ConfigMap retained')
    docs, gateway_receipt = patch_gateway(docs, registry + lock['images']['app'])
    docs, seed_objects, redactor_deployment = patch_redactor(docs, OVERLAY, run_id)
    docs = patch_ops(docs, OVERLAY / 'ops_server_assessment.py')
    docs = disposable_changes(docs, run_id)
    from agent_platform import onboarding, release_facts
    release_facts.install(docs, onboarding.load_all(), lock, private_values=(project,))
    release_facts.verify(docs)
    keys = [identity(doc) for doc in docs]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate Kubernetes object')
    route = next(d for d in docs if d['kind'] == 'ConfigMap'
                 and d['metadata']['name'].startswith('gateway-config-'))
    if 'vertex_ai/' in json.dumps(docs) or 'vertex_ai/' in route['data']['litellm.yaml']:
        raise ValueError('external LLM route retained')
    if 'PORTFOLIO_' + project in json.dumps(docs):
        raise ValueError('rendered environment corruption retained')
    if any(d['kind'] == 'FQDNNetworkPolicy' and d['metadata']['name'] == 'gateway-provider'
           for d in docs):
        raise ValueError('external gateway egress retained')
    receipt = {'run_id': run_id, 'platform_commit': lock['source_commit'],
        'main_render_sha256': hashlib.sha256(source_text.encode()).hexdigest(),
        'objects': len(docs), 'gateway': gateway_receipt,
        'seed_objects': [identity(d) for d in seed_objects],
        'redactor_deployment': identity(redactor_deployment),
        'image_digests': lock['images'], 'external_llm_route': False}
    receipt['runtime_registry'] = registry
    return docs, receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kubectl', default='kubectl')
    parser.add_argument('--images-lock', type=Path, required=True)
    parser.add_argument('--project-id', default=os.environ.get('ASSESSMENT_PROJECT_ID'))
    args = parser.parse_args()
    runtime_registry = os.environ.get('ASSESSMENT_RUNTIME_REGISTRY')
    if not runtime_registry:
        raise SystemExit('exact runtime registry required in ASSESSMENT_RUNTIME_REGISTRY')
    output = args.output.resolve()
    if output.is_relative_to(ROOT.resolve()):
        raise SystemExit('assessment manifest contains credentials; output outside repository required')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(args.output.parent, 0o700)
    passphrase = secrets.token_urlsafe(32)
    users = {}
    docs, receipt = make_bundle(args.run_id, args.kubectl, project=args.project_id,
                                images_lock=args.images_lock, passphrase=passphrase,
                                users_out=users, runtime_registry=runtime_registry)
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
    print(json.dumps({key: receipt[key] for key in
                      ('run_id', 'platform_commit', 'bundle_sha256', 'objects', 'external_llm_route')},
                     sort_keys=True))


if __name__ == '__main__':
    main()
