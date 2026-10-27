"""The independent janitor refuses the original project and keeps cleaning up on drift."""
from datetime import datetime, timedelta, timezone
import subprocess
import unittest
from unittest import mock

from cloud_wait import Waiter
from janitor import (JANITOR_IDENTITY_SECONDS, cleanup, gcloud_json, main as janitor_main,
                     validate_janitor_identity, wait_for_janitor_identity, wait_until_deadline)


PROJECT = 'sfai-assess-fixture01'
RUN = 'assess-0123456789abcdef'
MANIFEST = {'disposable_project_id': PROJECT, 'run_id': RUN}


class CloudFixture:
    def __init__(self, *, label=RUN, resources=0):
        self.label = label
        self.resources = resources
        self.billing = True
        self.deleted = False
        self.commands = []

    def __call__(self, *args):
        self.commands.append(args)
        if args[:2] == ('projects', 'describe') and getattr(self, 'unreadable', 0):
            self.unreadable -= 1
            raise RuntimeError('janitor:gcloud_failed:projects:describe')
        if args[:2] == ('projects', 'describe'):
            return {'projectId': PROJECT, 'labels': {'assessment_run': self.label},
                    'projectNumber': '123456789012',
                    'lifecycleState': 'DELETE_REQUESTED' if self.deleted else 'ACTIVE'}
        if args[:3] == ('billing', 'projects', 'describe'):
            return {'billingEnabled': self.billing,
                    'billingAccountName': 'billingAccounts/fixture' if self.billing else ''}
        if args[:3] == ('billing', 'projects', 'unlink'):
            self.billing = False
            return None
        if args[:2] == ('projects', 'delete'):
            self.deleted = True
            return None
        if 'list' in args:
            return [{}] * self.resources
        raise AssertionError(args)


class JanitorTest(unittest.TestCase):
    def test_zero_resources_unlinks_billing_before_delete(self):
        cloud = CloudFixture()
        receipt = cleanup(MANIFEST, call=cloud, now=datetime(2026, 10, 26, tzinfo=timezone.utc))
        self.assertEqual(receipt['result'], 'PASS')
        self.assertTrue(receipt['resource_absence'])
        self.assertLess(cloud.commands.index(('billing', 'projects', 'unlink', PROJECT, '--quiet')),
                        cloud.commands.index(('projects', 'delete', PROJECT, '--quiet')))

    def test_unexpected_resources_still_trigger_billing_unlink_and_delete(self):
        cloud = CloudFixture(resources=1)
        receipt = cleanup(MANIFEST, call=cloud)
        self.assertEqual(receipt['result'], 'TAKEOVER')
        self.assertFalse(receipt['resource_absence'])
        self.assertTrue(receipt['billing_unlinked'])
        self.assertTrue(receipt['project_delete_requested'])

    def test_wrong_run_label_blocks_every_mutation(self):
        cloud = CloudFixture(label='different-run')
        with self.assertRaisesRegex(RuntimeError, 'project_identity_mismatch'):
            cleanup(MANIFEST, call=cloud)
        self.assertEqual(cloud.commands, [('projects', 'describe', PROJECT)])

    def test_independent_watch_waits_until_deadline(self):
        times = iter([datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc),
                      datetime(2026, 10, 26, 0, 1, tzinfo=timezone.utc)])
        sleeps = []
        wait_until_deadline({'run_id': RUN, 'deadline_at': '2026-10-26T00:01:00+00:00'},
                            now=lambda: next(times), sleep=sleeps.append)
        self.assertEqual(sleeps, [60])

    def test_janitor_identity_must_belong_to_disposable_project(self):
        cloud = CloudFixture()
        provider = ('projects/123456789012/locations/global/workloadIdentityPools/'
                    'assessment-janitor/providers/assessment-janitor')
        service_account = 'assessment-janitor@' + PROJECT + '.iam.gserviceaccount.com'
        self.assertEqual(validate_janitor_identity(PROJECT, RUN, provider, service_account,
                                                   call=cloud)['projectNumber'], '123456789012')
        with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
            validate_janitor_identity(PROJECT, RUN, provider.replace('123456789012', '999999999999'),
                                      service_account, call=cloud)
        self.assertEqual([command for command in cloud.commands if command[:2] == ('projects', 'delete')], [])


    def test_janitor_identity_waits_for_iam_propagation_within_its_window(self):
        now = [datetime(2026, 10, 26, tzinfo=timezone.utc)]

        def sleep(seconds):
            now[0] += timedelta(seconds=seconds)
        provider = ('projects/123456789012/locations/global/workloadIdentityPools/'
                    'assessment-janitor/providers/assessment-janitor')
        service_account = 'assessment-janitor@' + PROJECT + '.iam.gserviceaccount.com'
        deadline = '2026-10-26T03:00:00+00:00'

        def wait(cloud, account_provider=provider):
            return wait_for_janitor_identity(PROJECT, RUN, account_provider, service_account,
                                             deadline_at=deadline, call=cloud,
                                             waiter=Waiter(deadline, clock=lambda: now[0], sleep=sleep))
        cloud = CloudFixture()
        cloud.unreadable = 3
        self.assertEqual(wait(cloud)['projectNumber'], '123456789012')
        self.assertEqual(len(cloud.commands), 4)
        cloud = CloudFixture()
        with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
            wait(cloud, provider.replace('123456789012', '999999999999'))
        self.assertEqual(len(cloud.commands), 1)
        # Still unusable after 15 minutes: the wait ends there, long before the deadline.
        cloud, started = CloudFixture(), now[0]
        cloud.unreadable = 10 ** 6
        with self.assertRaisesRegex(RuntimeError, 'retry_exhausted:janitor_identity'):
            wait(cloud)
        self.assertGreaterEqual(now[0] - started, timedelta(seconds=JANITOR_IDENTITY_SECONDS))
        self.assertLess(now[0] - started, timedelta(seconds=JANITOR_IDENTITY_SECONDS + 60))

    def test_unusable_janitor_identity_fails_the_job_visibly(self):
        argv = ['janitor.py', '--project-id', PROJECT, '--run-id', RUN,
                '--deadline-at', '2026-10-26T03:00:00+00:00',
                '--workload-identity-provider', 'provider', '--service-account', 'account',
                '--execute', '--watch']
        with mock.patch('sys.argv', argv), \
                mock.patch('janitor.wait_for_janitor_identity',
                           side_effect=RuntimeError('assessment:retry_exhausted:janitor_identity')), \
                mock.patch('janitor.wait_until_deadline') as watch, mock.patch('janitor.cleanup') as clean:
            with self.assertRaises(SystemExit) as raised:
                janitor_main()
        self.assertIn('janitor:identity_unusable', str(raised.exception.code))
        watch.assert_not_called()
        clean.assert_not_called()

    def test_slow_gcloud_call_is_a_runtime_error_so_cleanup_continues(self):
        with mock.patch('janitor.subprocess.run', side_effect=subprocess.TimeoutExpired(['gcloud'], 60)):
            with self.assertRaisesRegex(RuntimeError, 'gcloud_timeout:projects:delete'):
                gcloud_json('projects', 'delete', PROJECT, '--quiet')


if __name__ == '__main__':
    unittest.main()
