"""Copies use the same seven manifest digests only after source cryptographic gates."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cloud_wait import Waiter
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
        self.run = run

    def signature(self, ref):
        self.run(['cosign', 'verify', ref])
        return True

    def attestation(self, ref):
        return True

    def provenance(self, ref, **kwargs):
        return True


class CommandFixture:
    def __init__(self, images, *, copy_failures=0):
        self.images = images
        self.calls = []
        self.configs = []
        self.copy_failures = copy_failures

    def __call__(self, args, *, env=None, input=None, timeout=None):
        self.calls.append(args)
        self.configs.append((args[0], (env or {}).get('DOCKER_CONFIG')))
        if args[1] == 'copy' and self.copy_failures:
            self.copy_failures -= 1
            return 1, ''
        if args[0] == 'gcloud':
            return 0, 'synthetic-token\n'
        if args[1:3] == ['auth', 'login']:
            self.login_input = input
            return 0, ''
        if args[1] == 'digest':
            name = args[2].split('/')[-1].split(':')[0]
            return 0, self.images[next(k for k, v in IMAGE_NAMES.items() if v == name)].split('@')[1]
        return 0, ''


def waiter():
    now = [datetime(2026, 10, 26, tzinfo=timezone.utc)]

    def sleep(seconds):
        now[0] += timedelta(seconds=seconds)
    return Waiter('2026-10-26T03:00:00+00:00', clock=lambda: now[0], sleep=sleep)


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
        manifest = {'disposable_project_id': PROJECT, 'deadline_at': '2026-10-26T03:00:00+00:00',
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
                                  verifier_factory=VerifierFixture, waiter=waiter())
            self.assertEqual(receipt['same_digest_copies'], manifest['image_digests'])
            self.assertEqual(len([item for item in calls.calls if item[1] == 'copy']), 7)
            self.assertEqual(calls.login_input, 'synthetic-token\n')

    def test_cosign_uses_the_private_registry_config_and_tokens_are_refreshed(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            lock, manifest = self.fixture(directory)
            calls = CommandFixture(manifest['image_digests'])
            copy_images(manifest, lock, directory, run=calls, verifier_factory=VerifierFixture,
                        waiter=waiter())
            configs = {config for _, config in calls.configs}
            self.assertEqual(len(configs), 1)
            self.assertTrue(next(iter(configs)).startswith(str(directory)))
            self.assertIn(('cosign', next(iter(configs))), calls.configs)
            self.assertEqual(len([item for item in calls.calls if item[1:3] == ['auth', 'login']]), 8)

    def test_transient_copy_failure_is_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            lock, manifest = self.fixture(directory)
            calls = CommandFixture(manifest['image_digests'], copy_failures=2)
            receipt = copy_images(manifest, lock, directory, run=calls, verifier_factory=VerifierFixture,
                                  waiter=waiter())
            self.assertEqual(len(receipt['same_digest_copies']), 7)
            self.assertEqual(len([item for item in calls.calls if item[1] == 'copy']), 9)

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
