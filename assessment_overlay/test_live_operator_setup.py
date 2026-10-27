"""Disposable setup gives the independent janitor its limited project roles first."""
from datetime import datetime, timedelta, timezone
import unittest

from cloud_wait import Waiter
from operator_setup import JANITOR_ROLES, SERVICES, setup_project


PROJECT = 'sfai-assess-fixture01'
RUN = 'assess-0123456789abcdef'
MANIFEST = {'disposable_project_id': PROJECT, 'run_id': RUN,
            'deadline_at': '2026-10-26T03:00:00+00:00'}
BILLING = 'ABCDEF-123456-ABCDEF'
START = datetime(2026, 10, 26, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


def waiter(clock=None):
    clock = clock or Clock()
    return Waiter(MANIFEST['deadline_at'], clock=clock, sleep=clock.sleep)


class CloudFixture:
    def __init__(self, *, fail_enable=False, enable_times_out=False, enabled_after_polls=1,
                 create_times_out=False, binding_failures=0, never_enabled=False,
                 create_fails=False, create_exists=False, describe_lag=0):
        self.commands = []
        self.created = False
        self.billing = False
        self.deleted = False
        self.enabled = False
        self.default_network = True
        self.fail_enable = fail_enable
        self.enable_times_out = enable_times_out
        self.enabled_after_polls = enabled_after_polls
        self.enable_timeouts = []
        self.create_times_out = create_times_out
        self.binding_failures = binding_failures
        self.never_enabled = never_enabled
        self.create_fails = create_fails
        self.create_exists = create_exists
        self.describe_lag = describe_lag

    def __call__(self, *args, timeout=None):
        self.commands.append(args)
        if args[:2] == ('projects', 'create'):
            if self.create_fails:
                self.created = self.create_exists
                raise RuntimeError('janitor:gcloud_failed:projects:create')
            self.created = True
            if self.create_times_out:
                raise RuntimeError('janitor:gcloud_timeout:projects:create')
            return {}
        if args[:2] == ('projects', 'add-iam-policy-binding'):
            if self.binding_failures:
                self.binding_failures -= 1
                raise RuntimeError('fixture service account not yet known to IAM')
            return {}
        if args[:3] == ('billing', 'projects', 'link'):
            self.billing = True
            return {}
        if args[:2] == ('services', 'enable'):
            self.enable_timeouts.append(timeout)
            if self.fail_enable:
                raise RuntimeError('janitor:gcloud_failed:services:enable')
            if self.enable_times_out:
                raise RuntimeError('janitor:gcloud_timeout:services:enable')
            return {}
        if args[:3] == ('services', 'list', '--enabled'):
            self.enabled_after_polls -= 1
            ready = self.enabled_after_polls <= 0 and not self.never_enabled
            return [{'config': {'name': name}, 'state': 'ENABLED'} for name in SERVICES] if ready else []
        if args[:2] == ('projects', 'describe'):
            if self.describe_lag:
                self.describe_lag -= 1
                raise RuntimeError('janitor:gcloud_failed:projects:describe')
            if not self.created:
                raise RuntimeError('janitor:gcloud_failed:projects:describe')
            return {'projectId': PROJECT, 'labels': {'assessment_run': RUN},
                    'projectNumber': '123456789012',
                    'lifecycleState': 'DELETE_REQUESTED' if self.deleted else 'ACTIVE'}
        if args[:3] == ('compute', 'networks', 'list'):
            return [{'name': 'default'}] if self.default_network else []
        if args[:3] == ('compute', 'firewall-rules', 'list'):
            return [{'name': 'default-allow-ssh', 'network': 'projects/x/global/networks/default'}] \
                if self.default_network else []
        if args[:3] == ('compute', 'firewall-rules', 'delete'):
            return {}
        if args[:3] == ('compute', 'networks', 'delete'):
            self.default_network = False
            return {}
        if args[:2] == ('iam', 'service-accounts') or args[:2] == ('iam', 'workload-identity-pools'):
            return {}
        if args[:3] == ('billing', 'projects', 'describe'):
            return {'billingEnabled': self.billing,
                    'billingAccountName': 'billingAccounts/fixture' if self.billing else ''}
        if args[:3] == ('billing', 'projects', 'unlink'):
            self.billing = False
            return {}
        if args[:2] == ('projects', 'delete'):
            self.deleted = True
            return {}
        if 'list' in args:
            return []
        raise AssertionError(args)


def setup(cloud, wait=None):
    return setup_project(MANIFEST, billing_account=BILLING, call=cloud,
                         waiter=wait or waiter(), now=START)


class OperatorSetupTest(unittest.TestCase):
    def test_project_local_janitor_is_armed_before_setup_succeeds(self):
        cloud = CloudFixture()
        receipt = setup(cloud)
        self.assertEqual(receipt['janitor']['roles'], list(JANITOR_ROLES))
        self.assertEqual(receipt['janitor']['service_account'],
                         'assessment-janitor@' + PROJECT + '.iam.gserviceaccount.com')
        link = cloud.commands.index(('billing', 'projects', 'link', PROJECT,
                                     '--billing-account=' + BILLING, '--quiet'))
        grants = [i for i, args in enumerate(cloud.commands)
                  if args[:2] == ('projects', 'add-iam-policy-binding')]
        self.assertEqual(len(grants), 3)
        self.assertTrue(all(index > link for index in grants))
        self.assertEqual(cloud.commands[-1], ('billing', 'projects', 'describe', PROJECT))

    def test_services_enable_waits_synchronously_then_confirms_the_enabled_state(self):
        cloud = CloudFixture(enabled_after_polls=3)
        receipt = setup(cloud)
        self.assertEqual(receipt['services_enable'], 'completed')
        enable = [args for args in cloud.commands if args[:2] == ('services', 'enable')]
        self.assertEqual(enable, [('services', 'enable', *SERVICES, '--project=' + PROJECT, '--quiet')])
        self.assertEqual(cloud.enable_timeouts, [900])  # 15 minutes, well inside the deadline here.
        self.assertFalse([args for args in cloud.commands if args[:2] == ('services', 'operations')])
        lists = [i for i, args in enumerate(cloud.commands) if args[:3] == ('services', 'list', '--enabled')]
        self.assertEqual(len(lists), 3)
        account = next(i for i, args in enumerate(cloud.commands)
                       if args[:3] == ('iam', 'service-accounts', 'create'))
        self.assertLess(max(lists), account)

    def test_enable_timeout_is_bounded_by_the_deadline(self):
        clock = Clock()
        clock.now = datetime.fromisoformat(MANIFEST['deadline_at']) - timedelta(minutes=5)
        cloud = CloudFixture()
        setup_project(MANIFEST, billing_account=BILLING, call=cloud, waiter=waiter(clock), now=clock.now)
        self.assertLessEqual(cloud.enable_timeouts[0], 300)

    def test_client_timeout_falls_through_to_the_enabled_state(self):
        cloud = CloudFixture(enable_times_out=True, enabled_after_polls=2)
        receipt = setup(cloud)
        self.assertEqual(receipt['services_enable'], 'client_timeout')
        self.assertEqual(len([args for args in cloud.commands if args[:2] == ('services', 'enable')]), 1)

    def test_other_enable_error_is_final_and_cleans_up(self):
        cloud = CloudFixture(fail_enable=True)
        with self.assertRaisesRegex(RuntimeError, 'services_enable_failed'):
            setup(cloud)
        self.assertEqual(len([args for args in cloud.commands if args[:2] == ('services', 'enable')]), 1)
        self.assertFalse([args for args in cloud.commands if args[:3] == ('services', 'list', '--enabled')])
        self.assertFalse(cloud.billing)
        self.assertTrue(cloud.deleted)

    def test_services_wait_is_bounded_by_the_assessment_deadline(self):
        cloud, clock = CloudFixture(never_enabled=True), Clock()
        with self.assertRaisesRegex(RuntimeError, 'wait_timeout:services_enabled'):
            setup(cloud, waiter(clock))
        self.assertLessEqual(clock.now, datetime.fromisoformat(MANIFEST['deadline_at']))
        self.assertTrue(cloud.deleted)

    def test_slow_project_create_is_owned_only_through_its_run_label(self):
        cloud = CloudFixture(create_times_out=True, fail_enable=True)
        with self.assertRaisesRegex(RuntimeError, 'services_enable_failed'):
            setup(cloud)
        self.assertTrue(cloud.deleted)  # The labelled project was found, so it was cleaned up.

    def test_failed_create_stops_at_once_without_waiting_or_cleanup(self):
        cloud, clock = CloudFixture(create_fails=True), Clock()
        with self.assertRaisesRegex(RuntimeError, 'project_create_failed'):
            setup(cloud, waiter(clock))
        self.assertEqual(clock.now, START)  # No five-minute wait for a project that was never made.
        self.assertEqual([args[:2] for args in cloud.commands],
                         [('projects', 'create'), ('projects', 'describe')])
        self.assertFalse(cloud.billing)

    def test_create_error_after_the_operation_finished_still_uses_the_exact_project(self):
        cloud = CloudFixture(create_fails=True, create_exists=True)
        receipt = setup(cloud)
        self.assertTrue(receipt['project_label_verified'])

    def test_created_project_is_read_by_exact_id_through_read_lag(self):
        cloud, clock = CloudFixture(describe_lag=2), Clock()
        setup(cloud, waiter(clock))
        describes = [args for args in cloud.commands if args[:2] == ('projects', 'describe')]
        self.assertTrue(all(args == ('projects', 'describe', PROJECT) for args in describes))
        self.assertFalse([args for args in cloud.commands if args[:2] == ('projects', 'list')])
        baseline, plain = Clock(), CloudFixture()
        setup(plain, waiter(baseline))
        self.assertEqual((clock.now - START) - (baseline.now - START), timedelta(seconds=20))

    def test_iam_propagation_is_retried(self):
        cloud = CloudFixture(binding_failures=2)
        receipt = setup(cloud)
        self.assertEqual(receipt['janitor']['roles'], list(JANITOR_ROLES))
        grants = [args for args in cloud.commands if args[:2] == ('projects', 'add-iam-policy-binding')]
        self.assertEqual(len(grants), 5)

    def test_default_network_and_its_open_rules_are_removed(self):
        cloud = CloudFixture()
        receipt = setup(cloud)
        self.assertTrue(receipt['default_network_removed'])
        rule = cloud.commands.index(('compute', 'firewall-rules', 'delete', 'default-allow-ssh',
                                     '--project=' + PROJECT, '--quiet'))
        network = cloud.commands.index(('compute', 'networks', 'delete', 'default',
                                        '--project=' + PROJECT, '--quiet'))
        self.assertLess(rule, network)

    def test_invalid_inputs_make_no_cloud_calls(self):
        cloud = CloudFixture()
        with self.assertRaisesRegex(ValueError, 'declared billing account'):
            setup_project(MANIFEST, billing_account='invalid', call=cloud,
                          waiter=waiter(), now=START)
        self.assertEqual(cloud.commands, [])


if __name__ == '__main__':
    unittest.main()
