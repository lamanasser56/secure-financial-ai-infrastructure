"""Dispatch and prove the independent hosted janitor reached its watch step."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from urllib import request

from janitor import cleanup, load_manifest, write_receipt
from operator_setup import REPOSITORY


WORKFLOW = 'assessment-janitor.yml'
WAIT_STEP = 'Wait independently, then unlink billing and delete the disposable project'
API_ROOT = 'https://api.github.com/repos/' + REPOSITORY


def github_api(token, method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {'Accept': 'application/vnd.github+json',
               'Authorization': 'Bearer ' + token,
               'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'disposable-assessment-operator'}
    with request.urlopen(request.Request(API_ROOT + path, data=data, method=method,
                                         headers=headers), timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else None


def runs(api):
    result = api('GET', '/actions/workflows/' + WORKFLOW +
                 '/runs?branch=main&event=workflow_dispatch&per_page=100')
    if not isinstance(result, dict) or not isinstance(result.get('workflow_runs'), list):
        raise RuntimeError('assessment:janitor_runs_unreadable')
    return result['workflow_runs']


def arm(manifest, setup, *, api, now=None, sleep=time.sleep, timeout_seconds=300):
    now = now or datetime.now(timezone.utc)
    if now >= datetime.fromisoformat(manifest['deadline_at']):
        raise RuntimeError('assessment:deadline_passed')
    run_id = manifest['run_id']
    identity = setup.get('janitor', {})
    project = manifest['disposable_project_id']
    provider = identity.get('workload_identity_provider')
    sa = identity.get('service_account')
    if not isinstance(provider, str) or not provider.endswith(
            '/workloadIdentityPools/assessment-janitor/providers/assessment-janitor') \
            or sa != 'assessment-janitor@' + project + '.iam.gserviceaccount.com':
        raise ValueError('assessment:janitor_identity_missing')
    previous = {item['id'] for item in runs(api)}
    api('POST', '/actions/workflows/' + WORKFLOW + '/dispatches',
        {'ref': 'main', 'inputs': {
            'project_id': project, 'run_id': run_id,
            'deadline_at': manifest['deadline_at'],
            'workload_identity_provider': provider, 'service_account': sa}})
    started = time.monotonic()
    while time.monotonic() - started < timeout_seconds:
        matches = [item for item in runs(api) if item.get('id') not in previous
                   and item.get('display_title') == 'Janitor ' + run_id]
        if len(matches) > 1:
            raise RuntimeError('assessment:ambiguous_janitor_runs')
        if matches:
            run = matches[0]
            if run.get('status') == 'completed':
                raise RuntimeError('assessment:janitor_exited_before_watch')
            jobs = api('GET', '/actions/runs/' + str(run['id']) + '/jobs?per_page=100')
            for job in jobs.get('jobs', []):
                for step in job.get('steps', []):
                    if step.get('name') == WAIT_STEP and step.get('status') == 'in_progress':
                        return {'run_id': run_id, 'workflow_run_id': run['id'],
                                'watch_step_in_progress': True, 'started_at': now.isoformat()}
        sleep(10)
    raise RuntimeError('assessment:janitor_watch_not_confirmed')


def watch_running(run_id, workflow_run_id, *, api):
    """Recheck the independent janitor immediately before each live case."""
    run = api('GET', '/actions/runs/' + str(workflow_run_id))
    if (run.get('id') != workflow_run_id or run.get('display_title') != 'Janitor ' + run_id
            or run.get('event') != 'workflow_dispatch' or run.get('status') != 'in_progress'):
        return False
    jobs = api('GET', '/actions/runs/' + str(workflow_run_id) + '/jobs?per_page=100')
    return sum(step.get('name') == WAIT_STEP and step.get('status') == 'in_progress'
               for job in jobs.get('jobs', []) for step in job.get('steps', [])) == 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if not args.execute or not token:
        raise SystemExit('assessment:explicit_execute_and_github_token_required')
    manifest = load_manifest(args.run_dir / 'initial-manifest.json')
    setup = json.loads((args.run_dir / 'evidence/project-setup.json').read_text())
    try:
        receipt = arm(manifest, setup, api=lambda method, path, payload=None:
                      github_api(token, method, path, payload))
    except Exception:
        cleanup(manifest)
        raise
    write_receipt(args.run_dir / 'evidence/janitor-armed.json', receipt)
    print(json.dumps({'run_id': receipt['run_id'], 'watch_step_in_progress': True}))


if __name__ == '__main__':
    main()
