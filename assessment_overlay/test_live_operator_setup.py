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
OPERATION = 'operations/acat.p2-123456789012-fixture'
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
    def __init__(self, *, fail_enable=False, operation_polls=2, operation_error=False,
                 create_times_out=False, binding_failures=0, never_enabled=False):
        self.commands = []
        self.created = False
        self.billing = False
        self.deleted = False
        self.enabled = False
        self.default_network = True
        self.fail_enable = fail_enable
        self.operation_polls = operation_polls
        self.operation_error = operation_error
        self.create_times_out = create_times_out
        self.binding_failures = binding_failures
        self.never_enabled = never_enabled
        self.starts = []

    def start(self, project, services):
        self.starts.append((project, tuple(services)))
        if self.fail_enable:
            raise RuntimeError('fixture enable failure')
        return OPERATION

    def __call__(self, *args, timeout=None):
        self.commands.append(args)
        if args[:2] == ('projects', 'create'):
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
        if args[:3] == ('services', 'operations', 'describe'):
            self.operation_polls -= 1
            if self.operation_polls > 0:
                return {'name': OPERATION}
            if self.operation_error:
                return {'name': OPERATION, 'done': True, 'error': {'code': 9}}
            self.enabled = not self.never_enabled
            return {'name': OPERATION, 'done': True}
        if args[:3] == ('services', 'list', '--enabled'):
            return [{'config': {'name': name}, 'state': 'ENABLED'} for name in SERVICES] if self.enabled else []
        if args[:2] == ('projects', 'describe'):
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
    return setup_project(MANIFEST, billing_account=BILLING, call=cloud, start=cloud.start,
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

    def test_services_wait_on_the_enable_operation_then_the_enabled_state(self):
        cloud = CloudFixture(operation_polls=3)
        receipt = setup(cloud)
        self.assertTrue(receipt['services_operation_waited'])
        self.assertEqual(cloud.starts, [(PROJECT, SERVICES)])
        polls = [i for i, args in enumerate(cloud.commands)
                 if args[:3] == ('services', 'operations', 'describe')]
        self.assertEqual(len(polls), 3)
        enabled = cloud.commands.index(('services', 'list', '--enabled', '--project=' + PROJECT))
        self.assertGreater(enabled, max(polls))
        account = next(i for i, args in enumerate(cloud.commands)
                       if args[:3] == ('iam', 'service-accounts', 'create'))
        self.assertLess(enabled, account)

    def test_failed_enable_operation_cleans_up(self):
        cloud = CloudFixture(operation_error=True)
        with self.assertRaisesRegex(ValueError, 'services_enable_operation_failed'):
            setup(cloud)
        self.assertFalse(cloud.billing)
        self.assertTrue(cloud.deleted)

    def test_services_wait_is_bounded_by_the_assessment_deadline(self):
        cloud, clock = CloudFixture(never_enabled=True), Clock()
        with self.assertRaisesRegex(RuntimeError, 'wait_timeout:services_enabled'):
            setup(cloud, waiter(clock))
        self.assertLessEqual(clock.now, datetime.fromisoformat(MANIFEST['deadline_at']))
        self.assertTrue(cloud.deleted)

    def test_setup_failure_invokes_billing_unlink_and_project_delete(self):
        cloud = CloudFixture(fail_enable=True)
        with self.assertRaisesRegex(RuntimeError, 'retry_exhausted:services_enable_start'):
            setup(cloud)
        self.assertFalse(cloud.billing)
        self.assertTrue(cloud.deleted)

    def test_slow_project_create_is_owned_only_through_its_run_label(self):
        cloud = CloudFixture(create_times_out=True, fail_enable=True)
        with self.assertRaisesRegex(RuntimeError, 'services_enable_start'):
            setup(cloud)
        self.assertTrue(cloud.deleted)  # The labelled project was found, so it was cleaned up.

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
            setup_project(MANIFEST, billing_account='invalid', call=cloud, start=cloud.start,
                          waiter=waiter(), now=START)
        self.assertEqual(cloud.commands, [])
        self.assertEqual(cloud.starts, [])


if __name__ == '__main__':
    unittest.main()
