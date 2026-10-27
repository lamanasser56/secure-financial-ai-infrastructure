"""Failed cloud commands are kept privately in full; only a masked reason is printed."""
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

import cloud_log
from janitor import gcloud_json


DISPOSABLE = 'sfai-assess-0a1b2c3d4e'
ORIGINAL = 'project-fixture-original-01'
STDERR = ('Create in progress for [https://cloudresourcemanager.googleapis.com/v1/projects/%s].\n'
          'ERROR: (gcloud.projects.create) [someone@example.com] cannot create project %s under '
          'projects/%s (number 123456789012), billing account 0A1B2C-3D4E5F-6A7B8C, '
          'service account janitor@%s.%s\n') % (DISPOSABLE, DISPOSABLE, ORIGINAL, DISPOSABLE,
                                                 'iam.gservice' + 'account.com')
SECRETS = (DISPOSABLE, ORIGINAL, '123456789012', 'someone@example.com', '0A1B2C-3D4E5F-6A7B8C', 'janitor@')


class CloudLogTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(cloud_log._state.update, directory=None, secrets=(), last=None)
        cloud_log.configure(self.temp.name, {
            'disposable_project_id': DISPOSABLE,
            'source_registry': 'us-east1-docker.pkg.dev/' + ORIGINAL + '/sdp-evaluation-images/'})

    def records(self):
        path = Path(self.temp.name) / 'logs' / cloud_log.LOG_NAME
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_full_stderr_is_private_and_the_printed_reason_is_one_masked_line(self):
        out = io.StringIO()
        argv = ['gcloud', 'projects', 'create', DISPOSABLE, '--labels=assessment_run=assess-0123456789abcdef']
        line = cloud_log.failed(argv, 1, STDERR, stream=out)
        printed = out.getvalue()
        self.assertEqual(printed, line + '\n')
        self.assertTrue(line.startswith('cloud-failure: gcloud projects create <PROJECT> rc=1: ERROR:'))
        for secret in SECRETS:
            self.assertNotIn(secret, printed)
        record = self.records()[0]
        self.assertEqual(record['stderr'], STDERR)
        self.assertEqual(record['returncode'], 1)
        self.assertEqual(record['argv'], argv)

    def test_a_repeating_poll_failure_is_logged_each_time_but_printed_once(self):
        out = io.StringIO()
        for _ in range(3):
            cloud_log.failed(['gcloud', 'projects', 'describe', DISPOSABLE], 1, 'ERROR: not found', stream=out)
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertEqual(len(self.records()), 3)

    def test_gcloud_failure_and_timeout_are_recorded(self):
        failed = subprocess.CompletedProcess([], 1, stdout='', stderr=STDERR)
        err = io.StringIO()
        with mock.patch('janitor.subprocess.run', return_value=failed), mock.patch('sys.stderr', err):
            with self.assertRaisesRegex(RuntimeError, 'gcloud_failed:projects:create'):
                gcloud_json('projects', 'create', DISPOSABLE)
        timeout = subprocess.TimeoutExpired(['gcloud'], 60, stderr='Waiting for operation')
        with mock.patch('janitor.subprocess.run', side_effect=timeout), mock.patch('sys.stderr', err):
            with self.assertRaisesRegex(RuntimeError, 'gcloud_timeout:projects:create'):
                gcloud_json('projects', 'create', DISPOSABLE)
        records = self.records()
        self.assertEqual([record['returncode'] for record in records], [1, 'timeout'])
        self.assertEqual(records[0]['argv'][-1], '--format=json')
        for secret in SECRETS:
            self.assertNotIn(secret, err.getvalue())

    def test_without_a_run_folder_nothing_is_written(self):
        cloud_log._state.update(directory=None, secrets=(), last=None)
        out = io.StringIO()
        line = cloud_log.failed(['gcloud', 'projects', 'describe', DISPOSABLE], 1, STDERR, stream=out)
        self.assertFalse((Path(self.temp.name) / 'logs' / cloud_log.LOG_NAME).exists())
        for secret in SECRETS:
            self.assertNotIn(secret, line)


if __name__ == '__main__':
    unittest.main()
