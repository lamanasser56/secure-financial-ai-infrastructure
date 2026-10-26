"""Disposable admission signs only the seven copied immutable subjects."""
import unittest

from operator_admission import attest_copies


PROJECT = 'sfai-assess-fixture01'
RUN = 'assess-0123456789abcdef'
SOURCE = 'a' * 40
REGISTRY = 'us-east1-docker.pkg.dev/' + PROJECT + '/sdp-evaluation-images/'
IMAGES = {name: name + '@sha256:' + 'b' * 64 for name in (
    'gateway', 'database', 'redactor', 'app', 'ops-agent', 'agent-financial', 'platform-guide')}
MANIFEST = {'run_id': RUN, 'source_commit': SOURCE, 'disposable_project_id': PROJECT,
            'runtime_registry': REGISTRY, 'image_digests': IMAGES}
CLUSTER = {'run_id': RUN, 'source_commit': SOURCE,
           'attestor': 'projects/' + PROJECT + '/attestors/agent-platform-ci',
           'attestor_key_version': 'projects/' + PROJECT + '/locations/us-east1/'
                                   'keyRings/agent-platform/cryptoKeys/binauthz-attestor/cryptoKeyVersions/1'}
COPIES = {'run_id': RUN, 'source_commit': SOURCE,
          'runtime_registry': REGISTRY, 'same_digest_copies': IMAGES}


class VerifierFixture:
    def __init__(self, project, source, run):
        pass

    def attestation(self, ref):
        return True


class OperatorAdmissionTest(unittest.TestCase):
    def test_seven_exact_copies_get_new_verified_attestations(self):
        commands = []

        def run(args):
            commands.append(args)
            return 0, '{}'

        receipt = attest_copies(MANIFEST, CLUSTER, COPIES, run=run,
                                verifier_factory=VerifierFixture)
        self.assertEqual(len(receipt['cryptographically_verified_disposable_attestations']), 7)
        self.assertEqual(len(commands), 7)
        self.assertTrue(all('--artifact-url' in command for command in commands))

    def test_unverified_copy_refuses_signing(self):
        calls = []
        wrong = dict(COPIES, same_digest_copies=dict(IMAGES, app='app@sha256:' + 'c' * 64))
        with self.assertRaisesRegex(ValueError, 'receipt_mismatch'):
            attest_copies(MANIFEST, CLUSTER, wrong, run=lambda args: calls.append(args),
                          verifier_factory=VerifierFixture)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
