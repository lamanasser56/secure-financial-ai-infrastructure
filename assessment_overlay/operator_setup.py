"""Create the labelled disposable project and arm its independent janitor.

Project setup is a separate, explicit cloud-write phase. Each long-running or
eventually consistent step waits for its observable result, bounded by the
assessment deadline. On any setup error, the operator invokes the same
conservative cleanup path immediately.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

from cloud_wait import Waiter
from janitor import cleanup, gcloud_json, load_manifest, write_receipt
from render_live_bundle import assert_harness_unchanged


JANITOR_ROLES = ('roles/resourcemanager.projectDeleter', 'roles/billing.projectManager', 'roles/viewer')
SERVICES = (
    'artifactregistry.googleapis.com', 'binaryauthorization.googleapis.com',
    'cloudkms.googleapis.com', 'compute.googleapis.com', 'container.googleapis.com',
    'containeranalysis.googleapis.com', 'dlp.googleapis.com', 'dns.googleapis.com',
    'iam.googleapis.com', 'iamcredentials.googleapis.com', 'logging.googleapis.com', 'monitoring.googleapis.com',
    'networkconnectivity.googleapis.com', 'serviceusage.googleapis.com',
    'sts.googleapis.com',
)
BILLING_PATTERN = re.compile(r'[A-F0-9]{6}-[A-F0-9]{6}-[A-F0-9]{6}\Z')
REPOSITORY_ID = '1401417840'
REPOSITORY = 'lamanasser56/secure-financial-ai-infrastructure'
JANITOR_POOL = 'assessment-janitor'


OPERATION = re.compile(r'\b(operations/[A-Za-z0-9._:-]+)')
PROJECT_CREATE_SECONDS = 300
BILLING_SECONDS = 300
SERVICES_SECONDS = 900
DEFAULT_NETWORK_SECONDS = 180
IAM_SECONDS = 420


def start_services_enable(project, services):
    """Start one batch enable and return its long-running operation, or None if already done."""
    try:
        result = subprocess.run(['gcloud', 'services', 'enable', *services, '--project=' + project,
                                 '--async', '--quiet'], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise RuntimeError('operator:services_enable_start_timeout') from None
    if result.returncode:
        raise RuntimeError('operator:services_enable_start_failed')
    match = OPERATION.search(result.stderr + result.stdout)
    return match[1] if match else None


def enable_services(project, *, call, start, waiter):
    """Wait on the enable operation, then until every service reads as enabled."""
    operation = waiter.retry(lambda: start(project, SERVICES), seconds=SERVICES_SECONDS,
                             what='services_enable_start')
    if operation:
        def finished():
            value = call('services', 'operations', 'describe', operation)
            if value.get('error'):
                raise ValueError('operator:services_enable_operation_failed')
            return value.get('done') is True
        waiter.poll(finished, seconds=SERVICES_SECONDS, what='services_enable_operation')

    def enabled():
        names = {item.get('config', {}).get('name') or str(item.get('name', '')).rsplit('/', 1)[-1]
                 for item in call('services', 'list', '--enabled', '--project=' + project)
                 if item.get('state', 'ENABLED') == 'ENABLED'}
        return set(SERVICES) <= names
    waiter.poll(enabled, seconds=SERVICES_SECONDS, what='services_enabled')
    return operation is not None


def default_network_rules(project, call):
    return [rule['name'] for rule in call('compute', 'firewall-rules', 'list', '--project=' + project)
            if str(rule.get('network', '')).endswith('/networks/default')]


def has_default_network(project, call):
    return any(item.get('name') == 'default'
               for item in call('compute', 'networks', 'list', '--project=' + project))


def remove_default_network(project, *, call, waiter, appear_seconds=0):
    """Delete the auto-mode network (and its open firewall rules) that enabling Compute creates.

    The platform uses only its Terraform network; the default one would hold
    default-allow-ssh/rdp rules and keep the absence inventory from reaching zero.
    """
    if appear_seconds:
        try:
            waiter.poll(lambda: has_default_network(project, call), seconds=appear_seconds,
                        what='default_network_created')
        except RuntimeError:
            return False
    elif not has_default_network(project, call):
        return False
    for rule in default_network_rules(project, call):
        waiter.retry(lambda rule=rule: call('compute', 'firewall-rules', 'delete', rule,
                                            '--project=' + project, '--quiet', timeout=300),
                     seconds=IAM_SECONDS, what='default_firewall_rule_delete')
    waiter.retry(lambda: call('compute', 'networks', 'delete', 'default', '--project=' + project,
                              '--quiet', timeout=300),
                 seconds=IAM_SECONDS, what='default_network_delete')
    waiter.poll(lambda: not has_default_network(project, call), seconds=IAM_SECONDS,
                what='default_network_absent')
    return True


def ensure(create, exists, *, waiter, what):
    """Create once; a failed create is fine when the object exists, otherwise retry."""
    def attempt():
        try:
            create()
        except RuntimeError:
            if not exists():
                raise
    waiter.retry(attempt, seconds=IAM_SECONDS, what=what)
    waiter.poll(exists, seconds=IAM_SECONDS, what=what + '_visible')


def readable(call, *args):
    try:
        call(*args)
        return True
    except RuntimeError:
        return False


def arm_janitor(project, project_number, call, waiter):
    """Give only this disposable project an independent, workflow-bound janitor."""
    if not re.fullmatch(r'[0-9]{6,20}', str(project_number)):
        raise RuntimeError('operator:invalid_project_number')
    pool = JANITOR_POOL
    sa = f'assessment-janitor@{project}.iam.gserviceaccount.com'
    ensure(lambda: call('iam', 'service-accounts', 'create', 'assessment-janitor', '--project=' + project,
                        '--display-name=Disposable assessment cleanup', '--quiet'),
           lambda: readable(call, 'iam', 'service-accounts', 'describe', sa, '--project=' + project),
           waiter=waiter, what='janitor_service_account')
    ensure(lambda: call('iam', 'workload-identity-pools', 'create', pool, '--project=' + project,
                        '--location=global', '--display-name=Assessment janitor', '--quiet', timeout=300),
           lambda: readable(call, 'iam', 'workload-identity-pools', 'describe', pool,
                            '--project=' + project, '--location=global'),
           waiter=waiter, what='janitor_pool')
    condition = (f"assertion.repository_id == '{REPOSITORY_ID}' && "
                 "assertion.ref == 'refs/heads/main' && "
                 f"assertion.job_workflow_ref.startsWith('{REPOSITORY}/.github/workflows/assessment-janitor.yml@')")
    ensure(lambda: call('iam', 'workload-identity-pools', 'providers', 'create-oidc', pool,
                        '--project=' + project, '--location=global', '--workload-identity-pool=' + pool,
                        '--issuer-uri=https://token.actions.githubusercontent.com/',
                        '--attribute-mapping=google.subject=assertion.sub,attribute.repository_id=assertion.repository_id',
                        '--attribute-condition=' + condition, '--quiet', timeout=300),
           lambda: readable(call, 'iam', 'workload-identity-pools', 'providers', 'describe', pool,
                            '--project=' + project, '--location=global', '--workload-identity-pool=' + pool),
           waiter=waiter, what='janitor_provider')
    member = ('principalSet://iam.googleapis.com/projects/' + str(project_number) +
              '/locations/global/workloadIdentityPools/' + pool +
              '/attribute.repository_id/' + REPOSITORY_ID)
    # Policy bindings are idempotent; a new service account can be briefly unknown to IAM.
    waiter.retry(lambda: call('iam', 'service-accounts', 'add-iam-policy-binding', sa, '--project=' + project,
                              '--role=roles/iam.workloadIdentityUser', '--member=' + member, '--quiet'),
                 seconds=IAM_SECONDS, what='janitor_workload_identity_binding')
    for role in JANITOR_ROLES:
        waiter.retry(lambda role=role: call('projects', 'add-iam-policy-binding', project,
                                            '--member=serviceAccount:' + sa, '--role=' + role, '--quiet'),
                     seconds=IAM_SECONDS, what='janitor_project_binding')
    return {'service_account': sa,
            'workload_identity_provider': 'projects/' + str(project_number) +
            '/locations/global/workloadIdentityPools/' + pool + '/providers/' + pool,
            'roles': list(JANITOR_ROLES)}


def labelled_project(project, run_id, call):
    described = call('projects', 'describe', project)
    if (described.get('projectId') == project and described.get('lifecycleState') == 'ACTIVE'
            and described.get('labels', {}).get('assessment_run') == run_id):
        return described
    return None


def setup_project(manifest, *, billing_account, folder=None, call=gcloud_json,
                  start=start_services_enable, waiter=None, now=None):
    project, run_id = manifest['disposable_project_id'], manifest['run_id']
    if not BILLING_PATTERN.fullmatch(billing_account):
        raise ValueError('declared billing account required')
    deadline = datetime.fromisoformat(manifest['deadline_at'])
    now = now or datetime.now(timezone.utc)
    if deadline.tzinfo is None or now >= deadline:
        raise ValueError('assessment deadline passed')
    waiter = waiter or Waiter(manifest['deadline_at'])
    created = False
    try:
        args = ['projects', 'create', project, '--labels=assessment_run=' + run_id, '--quiet']
        if folder:
            args.append('--folder=' + str(folder))
        try:
            call(*args, timeout=waiter.timeout(PROJECT_CREATE_SECONDS))
        except RuntimeError:
            pass  # The create operation may still finish; only this run's label proves ownership.
        described = waiter.poll(lambda: labelled_project(project, run_id, call),
                                seconds=PROJECT_CREATE_SECONDS, what='project_create')
        created = True
        waiter.retry(lambda: call('billing', 'projects', 'link', project,
                                  '--billing-account=' + billing_account, '--quiet'),
                     seconds=BILLING_SECONDS, what='billing_link')
        waiter.poll(lambda: call('billing', 'projects', 'describe', project).get('billingEnabled') is True,
                    seconds=BILLING_SECONDS, what='billing_enabled')
        waited_on_operation = enable_services(project, call=call, start=start, waiter=waiter)
        default_removed = remove_default_network(project, call=call, waiter=waiter,
                                                 appear_seconds=DEFAULT_NETWORK_SECONDS)
        janitor = arm_janitor(project, described.get('projectNumber'), call, waiter)
        billing = call('billing', 'projects', 'describe', project)
        if billing.get('billingEnabled') is not True:
            raise RuntimeError('operator:billing_link_unconfirmed')
        return {'run_id': run_id, 'project_label_verified': True,
                'janitor': janitor, 'billing_linked': True,
                'services_enabled': list(SERVICES),
                'services_operation_waited': waited_on_operation,
                'default_network_removed': default_removed}
    except BaseException:
        if created:
            cleanup(manifest, call=call)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--billing-account', default=os.environ.get('ASSESSMENT_BILLING_ACCOUNT'))
    parser.add_argument('--folder', default=os.environ.get('ASSESSMENT_FOLDER'))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    manifest = load_manifest(args.run_dir / 'initial-manifest.json')
    assert_harness_unchanged(manifest)
    if not args.execute or not args.billing_account:
        raise SystemExit('operator:explicit_execute_and_inputs_required')
    receipt = setup_project(manifest, billing_account=args.billing_account, folder=args.folder)
    write_receipt(args.run_dir / 'evidence/project-setup.json', receipt)
    print(json.dumps({'run_id': receipt['run_id'], 'project_label_verified': True,
                      'janitor_grants': len(receipt['janitor']['roles']),
                      'billing_linked': True, 'services_enabled': len(receipt['services_enabled'])}))


if __name__ == '__main__':
    main()
