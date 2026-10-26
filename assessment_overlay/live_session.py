"""Create the private, source-bound twelve-case assessment session.

This is an offline preparation step. It never creates cloud resources or
contacts the deployment cluster. The operator starts the independent janitor
and verifies its receipt before any disposable project is used.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

from live_case_guard import CASE_LIMITS, PLANNED_LIMITS, SETUP_LIMITS, PROJECT_PATTERN, RUN_PATTERN
from render_live_bundle import ROOT, selected_source


HARD_LIMITS = (20, 60)
MANUAL_STOP = (12, 40)
COST_CEILING_USD = 50
MAX_SESSION_MINUTES = 180


def private_path(path):
    path = Path(path).expanduser().resolve()
    if path.is_relative_to(ROOT.resolve()):
        raise ValueError('assessment output must be outside the checkout')
    if path.exists():
        raise ValueError('assessment output already exists')
    return path


def session_manifest(project, lock, lock_path, run_id, now):
    if not PROJECT_PATTERN.fullmatch(project):
        raise ValueError('disposable assessment project required')
    if not RUN_PATTERN.fullmatch(run_id):
        raise ValueError('fresh assessment run ID required')
    source = selected_source(lock)
    return {
        'schema_version': 1,
        'run_id': run_id,
        'disposable_project_id': project,
        'source_commit': source,
        'images_lock_sha256': hashlib.sha256(Path(lock_path).read_bytes()).hexdigest(),
        'image_digests': lock['images'],
        'started_at': now.isoformat(),
        'deadline_at': (now + timedelta(minutes=MAX_SESSION_MINUTES)).isoformat(),
        'cost_ceiling_usd': COST_CEILING_USD,
        'external_llm_calls_allowed': 0,
        'hard_limits': list(HARD_LIMITS),
        'manual_stop': list(MANUAL_STOP),
        'setup_allocation': list(SETUP_LIMITS),
        'planned_limits': list(PLANNED_LIMITS),
        'case_allocations': {case: list(CASE_LIMITS[case]) for case in sorted(CASE_LIMITS)},
        'cleanup_required': ['resource_absence', 'billing_unlinked', 'project_delete_requested'],
    }


def write_private(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def prepare(*, project, images_lock, source_registry, output, kubectl='kubectl', now=None):
    output = private_path(output)
    lock_path = Path(images_lock).resolve()
    lock = json.loads(lock_path.read_text())
    run_id = 'assess-' + secrets.token_hex(8)
    now = now or datetime.now(timezone.utc)
    if not source_registry.startswith('us-east1-docker.pkg.dev/') or not source_registry.endswith('/sdp-evaluation-images/'):
        raise ValueError('reviewed source registry required')
    if source_registry == 'us-east1-docker.pkg.dev/' + project + '/sdp-evaluation-images/':
        raise ValueError('source registry must be separate from disposable project')
    manifest = session_manifest(project, lock, lock_path, run_id, now)
    manifest['source_registry'] = source_registry
    manifest['runtime_registry'] = 'us-east1-docker.pkg.dev/' + project + '/sdp-evaluation-images/'
    output.mkdir(mode=0o700, parents=True)
    bundle = output / 'bundle.yaml'
    env = dict(os.environ, ASSESSMENT_RUNTIME_REGISTRY=manifest['runtime_registry'])
    subprocess.run([sys.executable, '-B', str(ROOT / 'assessment_overlay/render_live_bundle.py'),
                    '--run-id', run_id, '--output', str(bundle), '--kubectl', kubectl,
                    '--images-lock', str(lock_path), '--project-id', project],
                   env=env, check=True, capture_output=True, text=True)
    subprocess.run([sys.executable, '-B', str(ROOT / 'assessment_overlay/stage_live_bundle.py'),
                    str(bundle), str(output / 'stages')],
                   check=True, capture_output=True, text=True)
    receipt = json.loads(bundle.with_suffix('.lock.json').read_text())
    if (receipt['platform_commit'] != manifest['source_commit']
            or receipt['runtime_registry'] != manifest['runtime_registry']
            or receipt['external_llm_route'] is not False):
        raise ValueError('assessment bundle does not match source/no-provider policy')
    manifest['bundle_sha256'] = receipt['bundle_sha256']
    write_private(output / 'initial-manifest.json', manifest)
    (output / 'evidence').mkdir(mode=0o700)
    print(json.dumps({'run_id': run_id, 'source_commit': manifest['source_commit'],
                      'bundle_sha256': manifest['bundle_sha256'], 'external_llm_calls_allowed': 0}))
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-id', default=os.environ.get('ASSESSMENT_PROJECT_ID'), required=False)
    parser.add_argument('--images-lock', type=Path, required=True)
    parser.add_argument('--source-registry', default=os.environ.get('ASSESSMENT_SOURCE_REGISTRY'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kubectl', default='kubectl')
    args = parser.parse_args()
    if not args.project_id or not args.source_registry:
        raise SystemExit('assessment project and source registry are required')
    prepare(project=args.project_id, images_lock=args.images_lock, source_registry=args.source_registry,
            output=args.output, kubectl=args.kubectl)


if __name__ == '__main__':
    main()
