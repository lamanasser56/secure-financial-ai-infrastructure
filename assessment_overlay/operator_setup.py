"""Create the labelled disposable project and arm its independent janitor.

Project setup is a separate, explicit cloud-write phase. On any setup error,
the operator invokes the same conservative cleanup path immediately.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from janitor import cleanup, gcloud_json, load_manifest, write_receipt


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


def arm_janitor(project, project_number, call):
    """Give only this disposable project an independent, workflow-bound janitor."""
    if not re.fullmatch(r'[0-9]{6,20}', str(project_number)):
        raise RuntimeError('operator:invalid_project_number')
    pool = JANITOR_POOL
    sa = f'assessment-janitor@{project}.iam.gserviceaccount.com'
    call('iam', 'service-accounts', 'create', 'assessment-janitor', '--project=' + project,
         '--display-name=Disposable assessment cleanup', '--quiet')
    call('iam', 'workload-identity-pools', 'create', pool, '--project=' + project,
         '--location=global', '--display-name=Assessment janitor', '--quiet')
    condition = (f"assertion.repository_id == '{REPOSITORY_ID}' && "
                 "assertion.ref == 'refs/heads/main' && "
                 f"assertion.job_workflow_ref.startsWith('{REPOSITORY}/.github/workflows/assessment-janitor.yml@')")
    call('iam', 'workload-identity-pools', 'providers', 'create-oidc', pool,
         '--project=' + project, '--location=global', '--workload-identity-pool=' + pool,
         '--issuer-uri=https://token.actions.githubusercontent.com/',
         '--attribute-mapping=google.subject=assertion.sub,attribute.repository_id=assertion.repository_id',
         '--attribute-condition=' + condition, '--quiet')
    member = ('principalSet://iam.googleapis.com/projects/' + str(project_number) +
              '/locations/global/workloadIdentityPools/' + pool +
              '/attribute.repository_id/' + REPOSITORY_ID)
    call('iam', 'service-accounts', 'add-iam-policy-binding', sa, '--project=' + project,
         '--role=roles/iam.workloadIdentityUser', '--member=' + member, '--quiet')
    for role in JANITOR_ROLES:
        call('projects', 'add-iam-policy-binding', project, '--member=serviceAccount:' + sa,
             '--role=' + role, '--quiet')
    return {'service_account': sa,
            'workload_identity_provider': 'projects/' + str(project_number) +
            '/locations/global/workloadIdentityPools/' + pool + '/providers/' + pool,
            'roles': list(JANITOR_ROLES)}


def setup_project(manifest, *, billing_account, folder=None, call=gcloud_json,
                  now=None):
    project, run_id = manifest['disposable_project_id'], manifest['run_id']
    if not BILLING_PATTERN.fullmatch(billing_account):
        raise ValueError('declared billing account required')
    deadline = datetime.fromisoformat(manifest['deadline_at'])
    now = now or datetime.now(timezone.utc)
    if deadline.tzinfo is None or now >= deadline:
        raise ValueError('assessment deadline passed')
    created = False
    try:
        args = ['projects', 'create', project, '--labels=assessment_run=' + run_id, '--quiet']
        if folder:
            args.append('--folder=' + str(folder))
        call(*args)
        created = True
        call('billing', 'projects', 'link', project, '--billing-account=' + billing_account, '--quiet')
        call('services', 'enable', *SERVICES, '--project=' + project, '--quiet')
        described = call('projects', 'describe', project)
        if described.get('projectId') != project or described.get('labels', {}).get('assessment_run') != run_id:
            raise RuntimeError('operator:project_identity_mismatch')
        janitor = arm_janitor(project, described.get('projectNumber'), call)
        billing = call('billing', 'projects', 'describe', project)
        if billing.get('billingEnabled') is not True:
            raise RuntimeError('operator:billing_link_unconfirmed')
        return {'run_id': run_id, 'project_label_verified': True,
                'janitor': janitor, 'billing_linked': True,
                'services_enabled': list(SERVICES)}
    except Exception:
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
    if not args.execute or not args.billing_account:
        raise SystemExit('operator:explicit_execute_and_inputs_required')
    receipt = setup_project(manifest, billing_account=args.billing_account, folder=args.folder)
    write_receipt(args.run_dir / 'evidence/project-setup.json', receipt)
    print(json.dumps({'run_id': receipt['run_id'], 'project_label_verified': True,
                      'janitor_grants': len(receipt['janitor']['roles']),
                      'billing_linked': True, 'services_enabled': len(receipt['services_enabled'])}))


if __name__ == '__main__':
    main()
