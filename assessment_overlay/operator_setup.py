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
    'iam.googleapis.com', 'logging.googleapis.com', 'monitoring.googleapis.com',
    'networkconnectivity.googleapis.com', 'serviceusage.googleapis.com',
)
SA_PATTERN = re.compile(r'[a-z][a-z0-9-]+@[a-z][a-z0-9-]+\.iam\.gserviceaccount\.com\Z')
BILLING_PATTERN = re.compile(r'[A-F0-9]{6}-[A-F0-9]{6}-[A-F0-9]{6}\Z')


def setup_project(manifest, *, billing_account, janitor_sa, folder=None, call=gcloud_json,
                  now=None):
    project, run_id = manifest['disposable_project_id'], manifest['run_id']
    if not SA_PATTERN.fullmatch(janitor_sa) or not BILLING_PATTERN.fullmatch(billing_account):
        raise ValueError('declared billing account and janitor service account required')
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
        member = 'serviceAccount:' + janitor_sa
        for role in JANITOR_ROLES:
            call('projects', 'add-iam-policy-binding', project, '--member=' + member,
                 '--role=' + role, '--quiet')
        call('billing', 'projects', 'link', project, '--billing-account=' + billing_account, '--quiet')
        call('services', 'enable', *SERVICES, '--project=' + project, '--quiet')
        described = call('projects', 'describe', project)
        if described.get('projectId') != project or described.get('labels', {}).get('assessment_run') != run_id:
            raise RuntimeError('operator:project_identity_mismatch')
        billing = call('billing', 'projects', 'describe', project)
        if billing.get('billingEnabled') is not True:
            raise RuntimeError('operator:billing_link_unconfirmed')
        return {'run_id': run_id, 'project_label_verified': True,
                'janitor_roles': list(JANITOR_ROLES), 'billing_linked': True,
                'services_enabled': list(SERVICES)}
    except Exception:
        if created:
            cleanup(manifest, call=call)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--billing-account', default=os.environ.get('ASSESSMENT_BILLING_ACCOUNT'))
    parser.add_argument('--janitor-sa', default=os.environ.get('ASSESSMENT_JANITOR_SA'))
    parser.add_argument('--folder', default=os.environ.get('ASSESSMENT_FOLDER'))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    manifest = load_manifest(args.run_dir / 'initial-manifest.json')
    if not args.execute or not args.billing_account or not args.janitor_sa:
        raise SystemExit('operator:explicit_execute_and_inputs_required')
    receipt = setup_project(manifest, billing_account=args.billing_account,
                            janitor_sa=args.janitor_sa, folder=args.folder)
    write_receipt(args.run_dir / 'evidence/project-setup.json', receipt)
    print(json.dumps({'run_id': receipt['run_id'], 'project_label_verified': True,
                      'janitor_grants': len(receipt['janitor_roles']),
                      'billing_linked': True, 'services_enabled': len(receipt['services_enabled'])}))


if __name__ == '__main__':
    main()
