"""Create the disposable cluster from the checked-in Terraform root and private state.

The operator must have armed the independent janitor before calling this module.
No Terraform state, plan, or provider credentials are written into the checkout:
the tracked root and module are copied into the private run directory, where a
backend_override.tf replaces the production GCS backend with private local state.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from cloud_wait import Waiter
from janitor import cleanup, gcloud_json, inspect_project, load_manifest, write_receipt
from render_live_bundle import ROOT
from source_selection import assert_harness_unchanged


TERRAFORM_SOURCE = 'platform/clouds/gke/terraform'
VERSION = re.compile(r'1\.3[5-9]\.[0-9]+-gke\.[0-9]+\Z')


APPLY_ATTEMPTS = 3
TERRAFORM_SECONDS = 3600


def private_config(tf_dir, *, root=ROOT):
    """Copy exactly the tracked Terraform root and module; add only a local backend override."""
    config = Path(tf_dir) / 'config'
    tracked = subprocess.run(['git', 'ls-files', '-z', '--', TERRAFORM_SOURCE + '/root',
                              TERRAFORM_SOURCE + '/module'], cwd=root, capture_output=True,
                             check=True).stdout.decode().split('\0')
    for name in filter(None, tracked):
        target = config / Path(name).relative_to(TERRAFORM_SOURCE)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(Path(root) / name, target)
    if not (config / 'root/backend.tf').is_file() or not (config / 'module').is_dir():
        raise RuntimeError('assessment:terraform_source_missing')
    (config / 'root/backend_override.tf').write_text(
        'terraform {\n  backend "local" {\n    path = %s\n  }\n}\n'
        % json.dumps(str(Path(tf_dir) / 'terraform.tfstate')))
    return config / 'root'


def run_terraform(command, *, data_dir, cwd, timeout=TERRAFORM_SECONDS):
    env = dict(os.environ, TF_DATA_DIR=str(data_dir), TF_IN_AUTOMATION='1')
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                                timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError('assessment:terraform_timeout:' + command[1]) from None
    # Keep Terraform's own diagnostics privately beside the state; they are never printed.
    logs = Path(data_dir).parent / 'logs'
    logs.mkdir(mode=0o700, exist_ok=True)
    log = logs / ('%02d-%s.log' % (len(list(logs.iterdir())), command[1]))
    with os.fdopen(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        stream.write(result.stderr if command[1] == 'show' else result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('assessment:terraform_failed:' + command[1])
    return result.stdout


def allowed_plan(value, *, resumed=False):
    """Return the managed create count; anything else that changes a resource is refused.

    A data source read deferred to apply (the KMS key version of a key created in
    the same apply) changes nothing. On a resumed apply, resources the failed
    attempt already created plan as no-op.
    """
    if value.get('format_version', '').split('.')[0] != '1':
        raise RuntimeError('assessment:unknown_terraform_plan_format')
    changes = value.get('resource_changes')
    if not isinstance(changes, list) or (not changes and not resumed):
        raise RuntimeError('assessment:empty_terraform_plan')
    creates = 0
    for item in changes:
        actions = item.get('change', {}).get('actions')
        if item.get('mode') == 'data' and actions == ['read']:
            continue
        if resumed and item.get('mode') == 'managed' and actions == ['no-op']:
            continue
        if item.get('mode') != 'managed' or actions != ['create']:
            raise RuntimeError('assessment:noncreate_terraform_plan')
        creates += 1
    if not creates and not resumed:
        raise RuntimeError('assessment:empty_terraform_plan')
    return creates


def create_cluster(manifest, run_dir, *, gke_version, terraform='terraform',
                   cloud=gcloud_json, runner=run_terraform, now=None, waiter=None,
                   configure=private_config):
    if not VERSION.fullmatch(gke_version):
        raise ValueError('assessment:exact_reviewed_gke_version_required')
    now = now or datetime.now(timezone.utc)
    if now >= datetime.fromisoformat(manifest['deadline_at']):
        raise ValueError('assessment:deadline_passed')
    waiter = waiter or Waiter(manifest['deadline_at'])
    run_dir = Path(run_dir).resolve()
    if run_dir.is_relative_to(ROOT.resolve()) or not (run_dir / 'initial-manifest.json').is_file():
        raise ValueError('assessment:private_run_directory_required')
    setup_path = run_dir / 'evidence/project-setup.json'
    janitor_path = run_dir / 'evidence/janitor-armed.json'
    if not setup_path.is_file() or not janitor_path.is_file():
        raise ValueError('assessment:independent_janitor_must_be_armed')
    setup = json.loads(setup_path.read_text())
    armed = json.loads(janitor_path.read_text())
    if (setup.get('run_id') != manifest['run_id'] or setup.get('billing_linked') is not True
            or armed.get('run_id') != manifest['run_id']
            or armed.get('watch_step_in_progress') is not True):
        raise ValueError('assessment:independent_janitor_must_be_armed')
    project, run_id = manifest['disposable_project_id'], manifest['run_id']
    described = inspect_project(project, run_id, cloud)
    project_number = str(described.get('projectNumber', ''))
    if not project_number.isdigit() or described.get('lifecycleState') != 'ACTIVE':
        raise RuntimeError('assessment:disposable_project_not_active')
    tf_dir = run_dir / 'terraform'
    tf_dir.mkdir(mode=0o700, exist_ok=False)
    plan = tf_dir / 'cluster.tfplan'
    data_dir = tf_dir / 'data'
    data_dir.mkdir(mode=0o700)
    config = configure(tf_dir)

    def terraform_run(*args, timeout=TERRAFORM_SECONDS):
        return runner([terraform, *args], data_dir=data_dir, cwd=config, timeout=timeout)

    terraform_run('init', '-input=false', '-lockfile=readonly', '-no-color')
    variables = [
        '-var=project_id=' + project,
        '-var=project_number=' + project_number,
        '-var=gke_version=' + gke_version,
        '-var=assessment_mode=true',
        '-var=deletion_protection=false',
    ]
    # A create can fail on propagation (new APIs, service agents, IAM). Re-planning
    # against the private state must still be create-only; nothing left means done.
    attempts, resources = 0, None
    while True:
        attempts += 1
        terraform_run('plan', '-input=false', '-no-color', '-out=' + str(plan), *variables)
        count = allowed_plan(json.loads(terraform_run('show', '-json', str(plan))),
                             resumed=attempts > 1)
        resources = count if resources is None else resources
        if not count:
            break
        try:
            terraform_run('apply', '-input=false', '-no-color', str(plan),
                          timeout=waiter.timeout(TERRAFORM_SECONDS))
            break
        except RuntimeError:
            if attempts >= APPLY_ATTEMPTS:
                raise
            waiter.sleep(30)
    outputs = json.loads(terraform_run('output', '-json'))
    platform = outputs.get('platform', {}).get('value', {})
    if (not platform.get('node_service_account') or not platform.get('attestor')
            or not platform.get('cluster_name') or not platform.get('cluster_location')):
        raise RuntimeError('assessment:terraform_outputs_incomplete')
    receipt = {'run_id': run_id, 'source_commit': manifest['source_commit'],
               'terraform_plan_sha256': hashlib.sha256(plan.read_bytes()).hexdigest(),
               'created_resource_count': resources, 'apply_attempts': attempts,
               'gke_version': gke_version,
               'cluster_name': platform['cluster_name'],
               'cluster_location': platform['cluster_location'],
               'node_service_account': platform['node_service_account'],
               'attestor': platform['attestor'],
               'attestor_key_version': platform['attestor_key_version'],
               'state_private': True}
    write_receipt(run_dir / 'evidence/cluster-setup.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--gke-version', required=True)
    parser.add_argument('--terraform', default='terraform')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit('assessment:explicit_execute_required')
    manifest = load_manifest(args.run_dir / 'initial-manifest.json')
    assert_harness_unchanged(manifest)
    try:
        receipt = create_cluster(manifest, args.run_dir, gke_version=args.gke_version,
                                 terraform=args.terraform)
    except BaseException:
        fallback = cleanup(manifest)
        write_receipt(args.run_dir / 'evidence/cluster-setup-fallback.json', fallback)
        raise
    print(json.dumps({'run_id': receipt['run_id'],
                      'created_resource_count': receipt['created_resource_count'],
                      'state_private': True}))


if __name__ == '__main__':
    main()
