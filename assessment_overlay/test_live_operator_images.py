"""Copies use the same seven manifest digests only after source cryptographic gates."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from operator_images import IMAGES, copy_images, source_subjects


PROJECT = 'sfai-assess-fixture01'
SOURCE_REGISTRY = 'us-east1-docker.pkg.dev/sfai-source-fixture01/sdp-evaluation-images/'
TARGET_REGISTRY = 'us-east1-docker.pkg.dev/' + PROJECT + '/sdp-evaluation-images/'
IMAGE_NAMES = {'gateway': 'agent-platform-gateway', 'database': 'agent-platform-database',
               'redactor': 'agent-platform-redactor', 'app': 'agent-platform-app',
               'ops-agent': 'agent-platform-ops', 'agent-financial': 'agent-financial',
               'platform-guide': 'platform-guide'}


class VerifierFixture:
    def __init__(self, project, source, run, *, cosign):
        self.calls = []

    def signature(self, ref):
        return True

    def attestation(self, ref):
        return True

    def provenance(self, ref, **kwargs):
        return True


class CommandFixture:
    def __init__(self, images):
        self.images = images
        self.calls = []

    def __call__(self, args, *, env=None, input=None):
        self.calls.append(args)
        if args[0] == 'gcloud':
            return 0, 'synthetic-token\n'
        if args[1:3] == ['auth', 'login']:
            self.login_input = input
            return 0, ''
        if args[1] == 'digest':
            name = args[2].split('/')[-1].split(':')[0]
            return 0, self.images[next(k for k, v in IMAGE_NAMES.items() if v == name)].split('@')[1]
        return 0, ''


class OperatorImagesTest(unittest.TestCase):
    def fixture(self, directory):
        images = {name: image + '@sha256:' + hashlib.sha256(name.encode()).hexdigest()
                  for name, image in IMAGE_NAMES.items()}
        lock = {'schema_version': 2, 'source_commit': 'a' * 40,
                'registry': 'us-east1-docker.pkg.dev/PROJECT_ID/sdp-evaluation-images/',
                'images': images, 'provenance': {name: {'git_archive_sha256': 'b' * 64,
                    'input_fingerprint': 'c' * 64, 'materials': []} for name in IMAGES}}
        path = directory / 'images.json'
        path.write_text(json.dumps(lock))
        manifest = {'disposable_project_id': PROJECT,
                    'run_id': 'assess-0123456789abcdef', 'source_commit': 'a' * 40,
                    'source_registry': SOURCE_REGISTRY, 'runtime_registry': TARGET_REGISTRY,
                    'images_lock_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'image_digests': images}
        return path, manifest

    def test_qualifies_then_copies_same_seven_digests(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            lock, manifest = self.fixture(directory)
            calls = CommandFixture(manifest['image_digests'])
            receipt = copy_images(manifest, lock, directory, run=calls,
                                  verifier_factory=VerifierFixture)
            self.assertEqual(receipt['same_digest_copies'], manifest['image_digests'])
            self.assertEqual(len([item for item in calls.calls if item[1] == 'copy']), 7)
            self.assertEqual(calls.login_input, 'synthetic-token\n')

    def test_modified_lock_or_target_refused_before_network(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            lock, manifest = self.fixture(directory)
            changed = dict(manifest, runtime_registry=SOURCE_REGISTRY)
            with self.assertRaisesRegex(ValueError, 'runtime_registry'):
                source_subjects(changed, lock)
            lock.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'image_lock_changed'):
                source_subjects(manifest, lock)


if __name__ == '__main__':
    unittest.main()
