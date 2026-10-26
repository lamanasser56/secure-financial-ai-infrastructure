"""Destroy only the disposable Terraform state, then invoke the janitor readback."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from janitor import cleanup, inspect_project, load_manifest, write_receipt
from operator_cluster import ROOT, run_terraform


def destroy(manifest, run_dir, *, terraform='terraform', cloud=inspect_project,
            runner=run_terraform, janitor=cleanup, now=None):
    run_dir = Path(run_dir).resolve()
    if run_dir.is_relative_to(ROOT.resolve()):
        raise ValueError('assessment:private_run_directory_required')
    project, run_id = manifest['disposable_project_id'], manifest['run_id']
    cloud(project, run_id)
    tf_dir = run_dir / 'terraform'
    state, data = tf_dir / 'terraform.tfstate', tf_dir / 'data'
    if not state.is_file() or not data.is_dir():
        raise RuntimeError('assessment:private_terraform_state_missing')
    plan = tf_dir / 'destroy.tfplan'
    command = [terraform]
    runner(command + ['plan', '-destroy', '-input=false', '-no-color',
                      '-state=' + str(state), '-out=' + str(plan)], data_dir=data)
    value = json.loads(runner(command + ['show', '-json', str(plan)], data_dir=data))
    if value.get('format_version', '').split('.')[0] != '1':
        raise RuntimeError('assessment:unknown_terraform_plan_format')
    changes = value.get('resource_changes')
    if not isinstance(changes, list) or not changes:
        raise RuntimeError('assessment:empty_destroy_plan')
    if any(item.get('mode') != 'managed' or item.get('change', {}).get('actions') != ['delete']
           for item in changes):
        raise RuntimeError('assessment:nondelete_destroy_plan')
    runner(command + ['apply', '-input=false', '-no-color', '-state=' + str(state), str(plan)],
           data_dir=data)
    result = janitor(manifest, now=now or datetime.now(timezone.utc))
    result['terraform_destroyed_resources'] = len(changes)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--terraform', default='terraform')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit('assessment:explicit_execute_required')
    manifest = load_manifest(args.run_dir / 'initial-manifest.json')
    try:
        result = destroy(manifest, args.run_dir, terraform=args.terraform)
    except Exception:
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
