"""Destroy only the disposable Terraform state, then invoke the janitor readback.

Before Terraform destroys the cluster, the assessment namespaces are deleted so
the CSI driver deletes the persistent disks it created; Terraform does not know
those disks. After the destroy, deletion is asynchronous, so the absence
inventory is polled to zero (bounded) before the janitor readback records it.
Cleanup is never bounded by the assessment deadline: it must also run after it.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from cloud_wait import Waiter
from janitor import cleanup, gcloud_json, inspect_project, load_manifest, resource_absence, write_receipt
from operator_cluster import ROOT, run_terraform
from operator_setup import remove_default_network


VOLUME_SECONDS = 900
ABSENCE_SECONDS = 900


def kubectl(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise RuntimeError('assessment:kubectl_timeout') from None
    if result.returncode:
        raise RuntimeError('assessment:kubectl_failed')
    return result.stdout


def drain_volumes(run_dir, run_id, *, kubectl_path, run, waiter):
    """Delete this run's namespaces and wait until every PersistentVolume (disk) is gone."""
    kubeconfig = Path(run_dir) / 'kube' / 'kubeconfig'
    if not kubeconfig.is_file():
        return 'no_cluster_access'
    base = [str(kubectl_path), '--kubeconfig=' + str(kubeconfig)]
    names = run(base + ['get', 'namespaces', '-l', 'assessment.run=' + run_id, '-o', 'name']).split()
    if names:
        run(base + ['delete', *names, '--wait=false'])
    waiter.poll(lambda: not json.loads(run(base + ['get', 'persistentvolumes', '-o', 'json']))['items'],
                seconds=VOLUME_SECONDS, what='persistent_volumes_deleted')
    return 'drained'


def delete_claim_disks(project, *, call, waiter):
    """Fallback: delete disks the CSI driver created for a claim if the cluster went first."""
    disks = [disk for disk in call('compute', 'disks', 'list', '--project=' + project)
             if 'kubernetes.io/created-for/pvc/name' in str(disk.get('description', ''))]
    for disk in disks:
        zone = str(disk.get('zone', '')).rsplit('/', 1)[-1]
        waiter.retry(lambda disk=disk, zone=zone: call('compute', 'disks', 'delete', disk['name'],
                                                       '--zone=' + zone, '--project=' + project,
                                                       '--quiet', timeout=300),
                     seconds=ABSENCE_SECONDS, what='claim_disk_delete')
    return len(disks)


def destroy(manifest, run_dir, *, terraform='terraform', kubectl_path='kubectl', cloud=inspect_project,
            runner=run_terraform, janitor=cleanup, call=gcloud_json, kube=kubectl, waiter=None, now=None):
    run_dir = Path(run_dir).resolve()
    if run_dir.is_relative_to(ROOT.resolve()):
        raise ValueError('assessment:private_run_directory_required')
    project, run_id = manifest['disposable_project_id'], manifest['run_id']
    cloud(project, run_id)
    waiter = waiter or Waiter()
    tf_dir = run_dir / 'terraform'
    state, data, config = tf_dir / 'terraform.tfstate', tf_dir / 'data', tf_dir / 'config' / 'root'
    if not state.is_file() or not data.is_dir() or not config.is_dir():
        raise RuntimeError('assessment:private_terraform_state_missing')
    try:
        volumes = drain_volumes(run_dir, run_id, kubectl_path=kubectl_path, run=kube, waiter=waiter)
    except RuntimeError:
        volumes = 'drain_failed'  # The disk fallback and the absence inventory still apply.
    plan = tf_dir / 'destroy.tfplan'

    def terraform_run(*args):
        return runner([terraform, *args], data_dir=data, cwd=config)

    terraform_run('plan', '-destroy', '-input=false', '-no-color', '-out=' + str(plan))
    value = json.loads(terraform_run('show', '-json', str(plan)))
    if value.get('format_version', '').split('.')[0] != '1':
        raise RuntimeError('assessment:unknown_terraform_plan_format')
    changes = value.get('resource_changes')
    if not isinstance(changes, list):
        raise RuntimeError('assessment:empty_destroy_plan')
    # Data sources only leave the state; every managed change must be a delete.
    managed = [item for item in changes if item.get('mode') != 'data']
    if not managed:
        raise RuntimeError('assessment:empty_destroy_plan')
    if any(item.get('mode') != 'managed' or item.get('change', {}).get('actions') != ['delete']
           for item in managed):
        raise RuntimeError('assessment:nondelete_destroy_plan')
    terraform_run('apply', '-input=false', '-no-color', str(plan))
    claim_disks = delete_claim_disks(project, call=call, waiter=waiter)
    remove_default_network(project, call=call, waiter=waiter)
    try:
        waiter.poll(lambda: all(count == 0 for count in resource_absence(project, call).values()),
                    seconds=ABSENCE_SECONDS, what='resource_absence')
    except RuntimeError:
        pass  # The janitor readback records what remains; billing unlink and deletion still run.
    result = janitor(manifest, now=now or datetime.now(timezone.utc))
    result['terraform_destroyed_resources'] = len(managed)
    result['volumes'] = volumes
    result['orphan_claim_disks_deleted'] = claim_disks
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--terraform', default='terraform')
    parser.add_argument('--kubectl', default='kubectl')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit('assessment:explicit_execute_required')
    manifest = load_manifest(args.run_dir / 'initial-manifest.json')
    try:
        result = destroy(manifest, args.run_dir, terraform=args.terraform, kubectl_path=args.kubectl)
    except BaseException:
        # Stop billing and request project deletion even when Terraform cannot finish.
        fallback = cleanup(manifest)
        write_receipt(args.run_dir / 'evidence/operator-cleanup-fallback.json', fallback)
        raise
    write_receipt(args.run_dir / 'evidence/operator-cleanup.json', result)
    print(json.dumps({'run_id': result['run_id'], 'result': result['result'],
                      'resource_absence': result['resource_absence'],
                      'billing_unlinked': result['billing_unlinked'],
                      'project_delete_requested': result['project_delete_requested']}))
    if result['result'] != 'PASS':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
