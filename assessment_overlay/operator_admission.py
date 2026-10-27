"""Sign fresh disposable BinAuthz attestations for the seven verified copy digests."""
import argparse
import json
from pathlib import Path

from agent_platform.release_verify import Verifier
from cloud_wait import Waiter
from janitor import load_manifest, write_receipt
from operator_images import IMAGES, command
from source_selection import assert_harness_unchanged


SIGN_SECONDS = 300
VERIFY_SECONDS = 120


def attest_copies(manifest, cluster, copies, *, run=command, verifier_factory=Verifier, waiter=None):
    run_id = manifest['run_id']
    if (cluster.get('run_id') != run_id or copies.get('run_id') != run_id
            or cluster.get('source_commit') != manifest['source_commit']
            or copies.get('source_commit') != manifest['source_commit']
            or copies.get('same_digest_copies') != manifest['image_digests']
            or copies.get('runtime_registry') != manifest['runtime_registry']
            or set(manifest['image_digests']) != IMAGES):
        raise ValueError('assessment:copy_or_cluster_receipt_mismatch')
    project = manifest['disposable_project_id']
    attestor = 'projects/' + project + '/attestors/agent-platform-ci'
    key = ('projects/' + project + '/locations/us-east1/keyRings/agent-platform/'
           'cryptoKeys/binauthz-attestor/cryptoKeyVersions/1')
    if cluster.get('attestor') != attestor or cluster.get('attestor_key_version') != key:
        raise ValueError('assessment:disposable_attestor_mismatch')
    refs = []
    waiter = waiter or Waiter(manifest.get('deadline_at'))
    verifier = verifier_factory(project, manifest['source_commit'], run)
    for name in sorted(IMAGES):
        ref = manifest['runtime_registry'] + manifest['image_digests'][name]

        def attested(ref=ref):
            try:
                return verifier.attestation(ref)
            except (RuntimeError, ValueError):
                return False

        attempts = []

        def sign(ref=ref, name=name):
            # A retried sign first checks for an occurrence an earlier attempt created,
            # because a second sign-and-create for the same digest is refused.
            if attempts and attested():
                return
            attempts.append(1)
            rc, _ = run(['gcloud', 'beta', 'container', 'binauthz', 'attestations',
                         'sign-and-create', '--project', project, '--artifact-url', ref,
                         '--attestor', attestor, '--keyversion', key])
            if rc:
                raise RuntimeError('assessment:disposable_attestation_sign_failed:' + name)
        # The attestor and its new KMS key can still be propagating right after Terraform.
        waiter.retry(sign, seconds=SIGN_SECONDS, what='attestation_sign:' + name)
        try:
            waiter.poll(attested, seconds=VERIFY_SECONDS, what='attestation_visible:' + name)
        except RuntimeError:
            raise RuntimeError('assessment:disposable_attestation_failed:' + name) from None
        refs.append(name)
    return {'run_id': run_id, 'attestor': attestor,
            'cryptographically_verified_disposable_attestations': refs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit('assessment:explicit_execute_required')
    manifest = load_manifest(args.run_dir / 'initial-manifest.json')
    assert_harness_unchanged(manifest)
    cluster = json.loads((args.run_dir / 'evidence/cluster-setup.json').read_text())
    copies = json.loads((args.run_dir / 'evidence/image-copy.json').read_text())
    result = attest_copies(manifest, cluster, copies)
    write_receipt(args.run_dir / 'evidence/disposable-admission.json', result)
    print(json.dumps({'run_id': result['run_id'],
                      'verified_attestations': len(result['cryptographically_verified_disposable_attestations'])}))


if __name__ == '__main__':
    main()
