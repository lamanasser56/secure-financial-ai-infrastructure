"""Qualify each source subject, then copy identical digests into the disposable registry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from agent_platform.release_verify import Verifier
from cloud_wait import Waiter
from janitor import load_manifest, write_receipt
from render_live_bundle import assert_harness_unchanged


REGISTRY = re.compile(r'us-east1-docker\.pkg\.dev/([a-z][a-z0-9-]{4,28}[a-z0-9])/sdp-evaluation-images/\Z')
IMAGES = {'gateway', 'database', 'redactor', 'app', 'ops-agent', 'agent-financial', 'platform-guide'}
DIGEST = re.compile(r'[a-z][a-z0-9-]+@sha256:[0-9a-f]{64}\Z')


COPY_SECONDS = 1800
COPY_RETRY_SECONDS = 300


def command(args, *, env=None, input=None, timeout=900):
    try:
        result = subprocess.run(args, capture_output=True, text=True, input=input, env=env,
                                timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, ''
    return result.returncode, result.stdout


def source_subjects(manifest, lock_path):
    lock_path = Path(lock_path)
    if hashlib.sha256(lock_path.read_bytes()).hexdigest() != manifest['images_lock_sha256']:
        raise ValueError('assessment:image_lock_changed')
    lock = json.loads(lock_path.read_text())
    if (lock.get('schema_version') != 2 or lock.get('source_commit') != manifest['source_commit']
            or lock.get('images') != manifest['image_digests']
            or lock.get('registry') != 'us-east1-docker.pkg.dev/PROJECT_ID/sdp-evaluation-images/'):
        raise ValueError('assessment:release_lock_mismatch')
    source = manifest.get('source_registry', '')
    match = REGISTRY.fullmatch(source)
    if not match or match[1] == manifest['disposable_project_id']:
        raise ValueError('assessment:source_registry_invalid')
    target = 'us-east1-docker.pkg.dev/' + manifest['disposable_project_id'] + '/sdp-evaluation-images/'
    if manifest.get('runtime_registry') != target or set(lock['images']) != IMAGES:
        raise ValueError('assessment:runtime_registry_or_image_set_invalid')
    if any(not DIGEST.fullmatch(value) for value in lock['images'].values()):
        raise ValueError('assessment:unpinned_image')
    return lock, match[1], source, target


def verify_source(lock, source, verifier):
    declarations = lock.get('provenance')
    if not isinstance(declarations, dict) or set(declarations) != IMAGES:
        raise ValueError('assessment:provenance_inventory_incomplete')
    for name in sorted(IMAGES):
        image = lock['images'][name]
        ref = source + image
        entry = declarations[name]
        if not verifier.signature(ref) or not verifier.attestation(ref):
            raise RuntimeError('assessment:source_signature_or_kms_attestation_failed:' + name)
        if not verifier.provenance(ref, image=image.split('@', 1)[0],
                                   archive_sha256=entry.get('git_archive_sha256'),
                                   input_fingerprint=entry.get('input_fingerprint'),
                                   materials=entry.get('materials')):
            raise RuntimeError('assessment:source_provenance_failed:' + name)


def copy_images(manifest, lock_path, run_dir, *, crane='crane', cosign='cosign', run=command,
                verifier_factory=Verifier, waiter=None):
    lock, source_project, source, target = source_subjects(manifest, lock_path)
    waiter = waiter or Waiter(manifest.get('deadline_at'))
    copied = {}
    # One private registry configuration serves cosign (source verification) and
    # crane, so neither reads the operator's personal Docker credential helper.
    with tempfile.TemporaryDirectory(prefix='assessment-registry-', dir=run_dir) as directory:
        env = dict(os.environ, DOCKER_CONFIG=directory)

        def registry_run(args, **kwargs):
            return run(args, env=env, **kwargs)

        def login():
            # Short-lived token: refreshed before each image, so a slow copy cannot outlive it.
            rc, token = run(['gcloud', 'auth', 'application-default', 'print-access-token'], env=env)
            if rc or not token.strip():
                raise RuntimeError('assessment:short_lived_registry_token_unavailable')
            rc, _ = run([crane, 'auth', 'login', 'us-east1-docker.pkg.dev',
                         '-u', 'oauth2accesstoken', '--password-stdin'],
                        env=env, input=token)
            if rc:
                raise RuntimeError('assessment:registry_login_failed')

        login()
        verifier = verifier_factory(source_project, manifest['source_commit'], registry_run, cosign=cosign)
        verify_source(lock, source, verifier)
        for name in sorted(IMAGES):
            image = lock['images'][name]
            tag = target + image.split('@', 1)[0] + ':' + manifest['run_id']

            def copy(image=image, tag=tag, name=name):
                login()
                rc, _ = run([crane, 'copy', source + image, tag], env=env,
                            timeout=waiter.timeout(COPY_SECONDS))
                if rc:
                    raise RuntimeError('assessment:image_copy_failed:' + name)
            # A copy is idempotent (same digest); a new repository can briefly refuse pushes.
            waiter.retry(copy, seconds=COPY_RETRY_SECONDS, what='image_copy:' + name)
            rc, got = run([crane, 'digest', tag], env=env)
            if rc or got.strip() != image.split('@', 1)[1]:
                raise RuntimeError('assessment:copied_digest_mismatch:' + name)
            copied[name] = image
    return {'run_id': manifest['run_id'], 'source_commit': manifest['source_commit'],
            'qualified_source_subjects': len(IMAGES), 'same_digest_copies': copied,
            'runtime_registry': target}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--images-lock', type=Path, required=True)
    parser.add_argument('--crane', default='crane')
    parser.add_argument('--cosign', default='cosign')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit('assessment:explicit_execute_required')
    manifest = load_manifest(args.run_dir / 'initial-manifest.json')
    assert_harness_unchanged(manifest)
    receipt = copy_images(manifest, args.images_lock, args.run_dir,
                          crane=args.crane, cosign=args.cosign)
    write_receipt(args.run_dir / 'evidence/image-copy.json', receipt)
    print(json.dumps({'run_id': receipt['run_id'],
                      'qualified_source_subjects': receipt['qualified_source_subjects'],
                      'same_digest_copies': len(receipt['same_digest_copies'])}))


if __name__ == '__main__':
    main()
