"""Apply the private assessed bundle in dependency order to its disposable GKE cluster."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import yaml

from cloud_wait import Waiter
from janitor import cleanup, load_manifest, write_receipt
from live_case_guard import read as read_ledgers
from render_live_bundle import ROOT
from source_selection import assert_harness_unchanged
from stage_live_bundle import key, split


sys.path.insert(0, str(ROOT / 'platform/clouds/gke'))
import lifecycle  # noqa: E402


API_SECONDS = 600
APPLY_SECONDS = 300


def kubectl(command, *, input=None):
    try:
        result = subprocess.run(command, input=input, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        raise RuntimeError('assessment:kubectl_timeout:' + command[2]) from None
    if result.returncode:
        raise RuntimeError('assessment:kubectl_failed:' + command[2])
    return result.stdout


def check_stages(run_dir, manifest):
    bundle = Path(run_dir) / 'bundle.yaml'
    if hashlib.sha256(bundle.read_bytes()).hexdigest() != manifest['bundle_sha256']:
        raise ValueError('assessment:bundle_changed')
    docs = [doc for doc in yaml.safe_load_all(bundle.read_text()) if doc]
    expected = split(docs)
    for index, stage in enumerate(expected):
        path = Path(run_dir) / 'stages' / ('stage-%d.yaml' % index)
        actual = [doc for doc in yaml.safe_load_all(path.read_text()) if doc]
        if actual != stage:
            raise ValueError('assessment:stage_changed:' + str(index))
    return expected


def run_apply(kubeconfig, stages, *, kubectl_path='kubectl', run=kubectl, waiter=None):
    waiter = waiter or Waiter()
    base = [str(kubectl_path), '--kubeconfig=' + str(kubeconfig)]
    # A new control plane (and its DNS endpoint) can answer before it is ready.
    waiter.retry(lambda: run(base + ['get', '--raw=/readyz']), seconds=API_SECONDS, what='api_server_ready')
    for index, docs in enumerate(stages):
        normal = [doc for doc in docs if doc['kind'] != 'NetworkLogging']
        addon = [doc for doc in docs if doc['kind'] == 'NetworkLogging']
        # Applies are idempotent; a just-created CRD or admission webhook may not serve yet.
        if normal:
            body = yaml.safe_dump_all(normal, sort_keys=False)
            waiter.retry(lambda body=body: run(base + ['apply', '--server-side', '--field-manager=assessment',
                                                       '-f', '-'], input=body),
                         seconds=APPLY_SECONDS, what='apply_stage_%d' % index)
        if addon:
            body = yaml.safe_dump_all(addon, sort_keys=False)
            waiter.retry(lambda body=body: run(base + ['apply', '-f', '-'], input=body),
                         seconds=APPLY_SECONDS, what='apply_addon_%d' % index)
        if index == 4:
            run(base + ['-n', 'platform', 'rollout', 'status', 'statefulset/postgres', '--timeout=600s'])
        if index == 5:
            run(base + ['-n', 'platform', 'wait', '--for=condition=complete',
                        'job/assessment-sdp-seed', '--timeout=600s'])
    run(base + ['-n', 'platform', 'wait', '--for=condition=complete', 'job/schema', '--timeout=600s'])
    for doc in stages[6]:
        if doc['kind'] == 'Deployment' and doc['spec'].get('replicas', 1) > 0:
            run(base + ['-n', doc['metadata']['namespace'], 'rollout', 'status',
                        'deployment/' + doc['metadata']['name'], '--timeout=600s'])
    return len({key(doc) for stage in stages for doc in stage})


def runtime_digests(pods, manifest, namespaces):
    expected = {name: image.split('@', 1)[1] for name, image in manifest['image_digests'].items()}
    seen = set()
    for pod in pods.get('items', []):
        if pod.get('metadata', {}).get('namespace') not in namespaces or pod.get('status', {}).get('phase') != 'Running':
            continue
        statuses = {item['name']: item for item in pod['status'].get('containerStatuses', [])}
        for container in pod['spec'].get('containers', []):
            image = container['image']
            if not image.startswith(manifest['runtime_registry']) or '@sha256:' not in image:
                raise RuntimeError('assessment:non_disposable_runtime_image')
            image_name = image.removeprefix(manifest['runtime_registry']).split('@', 1)[0]
            matches = [name for name, ref in manifest['image_digests'].items()
                       if ref.split('@', 1)[0] == image_name]
            if len(matches) != 1 or image.split('@', 1)[1] != expected[matches[0]]:
                raise RuntimeError('assessment:undeclared_runtime_image')
            actual = statuses.get(container['name'], {}).get('imageID', '')
            if not actual.endswith('@' + expected[matches[0]]):
                raise RuntimeError('assessment:runtime_digest_mismatch')
            seen.add(matches[0])
    if seen != set(expected):
        raise RuntimeError('assessment:runtime_image_inventory_incomplete')
    return sorted(seen)


def apply_bundle(manifest, run_dir, cluster, admission, *, kubectl_path='kubectl',
                 kubeconfig_for=lifecycle.kubeconfig_for, run=kubectl,
                 ledger_reader=read_ledgers, waiter=None):
    run_dir = Path(run_dir).resolve()
    if run_dir.is_relative_to(ROOT.resolve()):
        raise ValueError('assessment:private_run_directory_required')
    if (cluster.get('run_id') != manifest['run_id']
            or cluster.get('cluster_name') != 'agent-platform'
            or cluster.get('cluster_location') != 'us-east1-b'
            or admission.get('run_id') != manifest['run_id']
            or len(admission.get('cryptographically_verified_disposable_attestations', [])) != 7):
        raise ValueError('assessment:cluster_or_admission_receipt_invalid')
    stages = check_stages(run_dir, manifest)
    kubeconfig = kubeconfig_for(manifest['disposable_project_id'],
                                cluster['cluster_name'], cluster['cluster_location'],
                                run_dir / 'kube')
    objects = run_apply(kubeconfig, stages, kubectl_path=kubectl_path, run=run,
                        waiter=waiter or Waiter(manifest.get('deadline_at')))
    namespace_names = {doc['metadata']['name'] for doc in stages[0] if doc['kind'] == 'Namespace'}
    pod_data = json.loads(run([str(kubectl_path), '--kubeconfig=' + str(kubeconfig),
                               'get', 'pods', '--all-namespaces', '-o', 'json']))
    verified_images = runtime_digests(pod_data, manifest, namespace_names)
    initial = ledger_reader(kubeconfig, manifest['run_id'], kubectl_path)
    if initial['completed_redactions'] != 0 or initial['sdk_attempts'] != 0 or initial['inflight'] != 0:
        raise RuntimeError('assessment:initial_durable_counters_not_zero')
    return {'run_id': manifest['run_id'], 'source_commit': manifest['source_commit'],
            'bundle_sha256': manifest['bundle_sha256'], 'applied_objects': objects,
            'verified_runtime_images': verified_images,
            'initial_ledgers': initial, 'kubeconfig_private': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--kubectl', default='kubectl')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit('assessment:explicit_execute_required')
    manifest = load_manifest(args.run_dir / 'initial-manifest.json')
    assert_harness_unchanged(manifest)
    cluster = json.loads((args.run_dir / 'evidence/cluster-setup.json').read_text())
    admission = json.loads((args.run_dir / 'evidence/disposable-admission.json').read_text())
    try:
        receipt = apply_bundle(manifest, args.run_dir, cluster, admission,
                               kubectl_path=args.kubectl)
    except BaseException:  # lifecycle.kubeconfig_for exits with SystemExit on a gcloud failure.
        fallback = cleanup(manifest)
        write_receipt(args.run_dir / 'evidence/apply-fallback.json', fallback)
        raise
    write_receipt(args.run_dir / 'evidence/bundle-applied.json', receipt)
    print(json.dumps({'run_id': receipt['run_id'], 'applied_objects': receipt['applied_objects'],
                      'initial_redactions': 0, 'initial_sdk_attempts': 0}))


if __name__ == '__main__':
    main()
