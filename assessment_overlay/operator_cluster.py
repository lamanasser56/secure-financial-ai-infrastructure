"""Create the disposable cluster from the checked-in Terraform root and private state.

The operator must have armed the independent janitor before calling this module.
No Terraform state, plan, or provider credentials are written into the checkout.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from janitor import gcloud_json, inspect_project, load_manifest, write_receipt
from render_live_bundle import ROOT


ROOT_MODULE = ROOT / 'platform/clouds/gke/terraform/root'
VERSION = re.compile(r'1\.3[5-9]\.[0-9]+-gke\.[0-9]+\Z')


def run_terraform(command, *, data_dir, cwd=ROOT_MODULE):
    env = dict(os.environ, TF_DATA_DIR=str(data_dir), TF_IN_AUTOMATION='1')
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                            timeout=3600)
    if result.returncode:
        raise RuntimeError('assessment:terraform_failed:' + command[1])
    return result.stdout


def allowed_plan(value):
    if value.get('format_version', '').split('.')[0] != '1':
        raise RuntimeError('assessment:unknown_terraform_plan_format')
    changes = value.get('resource_changes')
    if not isinstance(changes, list) or not changes:
        raise RuntimeError('assessment:empty_terraform_plan')
    for item in changes:
        actions = item.get('change', {}).get('actions')
        if item.get('mode') != 'managed' or actions != ['create']:
            raise RuntimeError('assessment:noncreate_terraform_plan')
    return len(changes)


def create_cluster(manifest, run_dir, *, gke_version, terraform='terraform',
                   cloud=gcloud_json, runner=run_terraform, now=None):
    if not VERSION.fullmatch(gke_version):
        raise ValueError('assessment:exact_reviewed_gke_version_required')
    now = now or datetime.now(timezone.utc)
    if now >= datetime.fromisoformat(manifest['deadline_at']):
        raise ValueError('assessment:deadline_passed')
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
    state = tf_dir / 'terraform.tfstate'
    plan = tf_dir / 'cluster.tfplan'
    data_dir = tf_dir / 'data'
    data_dir.mkdir(mode=0o700)
    base = [terraform]
    runner(base + ['init', '-backend=false', '-lockfile=readonly', '-input=false', '-no-color'],
           data_dir=data_dir)
    variables = [
        '-var=project_id=' + project,
        '-var=project_number=' + project_number,
        '-var=gke_version=' + gke_version,
        '-var=assessment_mode=true',
        '-var=deletion_protection=false',
    ]
    runner(base + ['plan', '-input=false', '-no-color', '-state=' + str(state),
                   '-out=' + str(plan), *variables], data_dir=data_dir)
    plan_json = json.loads(runner(base + ['show', '-json', str(plan)], data_dir=data_dir))
    resources = allowed_plan(plan_json)
    runner(base + ['apply', '-input=false', '-no-color', '-state=' + str(state), str(plan)],
           data_dir=data_dir)
    outputs = json.loads(runner(base + ['output', '-json', '-state=' + str(state)],
                                data_dir=data_dir))
    platform = outputs.get('platform', {}).get('value', {})
    if not platform.get('node_service_account') or not platform.get('attestor'):
        raise RuntimeError('assessment:terraform_outputs_incomplete')
    receipt = {'run_id': run_id, 'source_commit': manifest['source_commit'],
               'terraform_plan_sha256': hashlib.sha256(plan.read_bytes()).hexdigest(),
               'created_resource_count': resources, 'gke_version': gke_version,
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
    receipt = create_cluster(manifest, args.run_dir, gke_version=args.gke_version,
                             terraform=args.terraform)
    print(json.dumps({'run_id': receipt['run_id'],
                      'created_resource_count': receipt['created_resource_count'],
                      'state_private': True}))


if __name__ == '__main__':
    main()
