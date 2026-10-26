"""Disposable setup gives the independent janitor its limited project roles first."""
from datetime import datetime, timezone
import unittest

from operator_setup import JANITOR_ROLES, setup_project


PROJECT = 'sfai-assess-fixture01'
RUN = 'assess-0123456789abcdef'
MANIFEST = {'disposable_project_id': PROJECT, 'run_id': RUN,
            'deadline_at': '2026-10-26T03:00:00+00:00'}
BILLING = 'ABCDEF-123456-ABCDEF'
SA = 'janitor@fixture-project.iam.gserviceaccount.com'


class CloudFixture:
    def __init__(self, fail_enable=False):
        self.commands = []
        self.created = False
        self.billing = False
        self.deleted = False
        self.fail_enable = fail_enable

    def __call__(self, *args):
        self.commands.append(args)
        if args[:2] == ('projects', 'create'):
            self.created = True
            return {}
        if args[:2] == ('projects', 'add-iam-policy-binding'):
            return {}
        if args[:3] == ('billing', 'projects', 'link'):
            self.billing = True
            return {}
        if args[:2] == ('services', 'enable'):
            if self.fail_enable:
                raise RuntimeError('fixture enable failure')
            return {}
        if args[:2] == ('projects', 'describe'):
            return {'projectId': PROJECT, 'labels': {'assessment_run': RUN},
                    'lifecycleState': 'DELETE_REQUESTED' if self.deleted else 'ACTIVE'}
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


class OperatorSetupTest(unittest.TestCase):
    def test_janitor_grants_precede_billing_link(self):
        cloud = CloudFixture()
        receipt = setup_project(MANIFEST, billing_account=BILLING, janitor_sa=SA, call=cloud,
                                now=datetime(2026, 10, 26, tzinfo=timezone.utc))
        self.assertEqual(receipt['janitor_roles'], list(JANITOR_ROLES))
        link = cloud.commands.index(('billing', 'projects', 'link', PROJECT,
                                     '--billing-account=' + BILLING, '--quiet'))
        grants = [i for i, args in enumerate(cloud.commands)
                  if args[:2] == ('projects', 'add-iam-policy-binding')]
        self.assertEqual(len(grants), 3)
        self.assertTrue(all(index < link for index in grants))

    def test_setup_failure_invokes_billing_unlink_and_project_delete(self):
        cloud = CloudFixture(fail_enable=True)
        with self.assertRaisesRegex(RuntimeError, 'fixture enable failure'):
            setup_project(MANIFEST, billing_account=BILLING, janitor_sa=SA, call=cloud,
                          now=datetime(2026, 10, 26, tzinfo=timezone.utc))
        self.assertFalse(cloud.billing)
        self.assertTrue(cloud.deleted)

    def test_invalid_inputs_make_no_cloud_calls(self):
        cloud = CloudFixture()
        with self.assertRaisesRegex(ValueError, 'declared billing account'):
            setup_project(MANIFEST, billing_account='invalid', janitor_sa=SA, call=cloud,
                          now=datetime(2026, 10, 26, tzinfo=timezone.utc))
        self.assertEqual(cloud.commands, [])


if __name__ == '__main__':
    unittest.main()
