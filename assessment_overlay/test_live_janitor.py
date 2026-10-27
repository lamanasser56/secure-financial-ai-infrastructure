"""The independent janitor refuses the original project and keeps cleaning up on drift."""
from datetime import datetime, timedelta, timezone
import subprocess
import unittest
from unittest import mock

from cloud_wait import Waiter
from janitor import cleanup, gcloud_json, validate_janitor_identity, wait_for_janitor_identity, wait_until_deadline


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


    def test_janitor_identity_waits_for_iam_propagation_within_the_deadline(self):
        now = [datetime(2026, 10, 26, tzinfo=timezone.utc)]

        def sleep(seconds):
            now[0] += timedelta(seconds=seconds)
        provider = ('projects/123456789012/locations/global/workloadIdentityPools/'
                    'assessment-janitor/providers/assessment-janitor')
        service_account = 'assessment-janitor@' + PROJECT + '.iam.gserviceaccount.com'
        deadline = '2026-10-26T03:00:00+00:00'
        cloud = CloudFixture()
        cloud.unreadable = 3
        described = wait_for_janitor_identity(PROJECT, RUN, provider, service_account, deadline_at=deadline,
                                              call=cloud, waiter=Waiter(deadline, clock=lambda: now[0],
                                                                        sleep=sleep))
        self.assertEqual(described['projectNumber'], '123456789012')
        self.assertEqual(len(cloud.commands), 4)
        cloud = CloudFixture()
        with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
            wait_for_janitor_identity(PROJECT, RUN, provider.replace('123456789012', '999999999999'),
                                      service_account, deadline_at=deadline, call=cloud,
                                      waiter=Waiter(deadline, clock=lambda: now[0], sleep=sleep))
        self.assertEqual(len(cloud.commands), 1)

    def test_slow_gcloud_call_is_a_runtime_error_so_cleanup_continues(self):
        with mock.patch('janitor.subprocess.run', side_effect=subprocess.TimeoutExpired(['gcloud'], 60)):
            with self.assertRaisesRegex(RuntimeError, 'gcloud_timeout:projects:delete'):
                gcloud_json('projects', 'delete', PROJECT, '--quiet')


if __name__ == '__main__':
    unittest.main()
