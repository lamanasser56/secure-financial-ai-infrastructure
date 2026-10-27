"""Only a janitor actively waiting on an independent runner arms a live run."""
from datetime import datetime, timezone
import unittest

from operator_janitor import WAIT_STEP, arm, watch_running


PROJECT = 'sfai-assess-fixture01'
RUN = 'assess-0123456789abcdef'
MANIFEST = {'disposable_project_id': PROJECT, 'run_id': RUN,
            'deadline_at': '2026-10-27T00:00:00+00:00'}
SETUP = {'janitor': {
    'workload_identity_provider': ('projects/123456789012/locations/global/'
                                   'workloadIdentityPools/assessment-janitor/'
                                   'providers/assessment-janitor'),
    'service_account': 'assessment-janitor@' + PROJECT + '.iam.gserviceaccount.com'}}


class GithubFixture:
    def __init__(self, *, step='in_progress', errors=0):
        self.dispatched = False
        self.calls = []
        self.step = step
        self.errors = errors

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if self.dispatched and method == 'GET' and self.errors:
            self.errors -= 1
            raise OSError('fixture transient GitHub API error')
        if method == 'POST':
            self.dispatched = True
            self.payload = payload
            return None
        if '/jobs?' in path:
            return {'jobs': [{'steps': [{'name': WAIT_STEP, 'status': self.step}]}]}
        if '/runs?' in path:
            return {'workflow_runs': [] if not self.dispatched else [
                {'id': 42, 'display_title': 'Janitor ' + RUN, 'status': 'in_progress'}]}
        if path == '/actions/runs/42':
            return {'id': 42, 'display_title': 'Janitor ' + RUN,
                    'event': 'workflow_dispatch', 'status': 'in_progress'}
        raise AssertionError(path)


class OperatorJanitorTest(unittest.TestCase):
    def test_dispatch_then_confirm_watch_step(self):
        api = GithubFixture()
        receipt = arm(MANIFEST, SETUP, api=api,
                      now=datetime(2026, 10, 26, tzinfo=timezone.utc))
        self.assertEqual(receipt['workflow_run_id'], 42)
        self.assertTrue(receipt['watch_step_in_progress'])
        self.assertEqual(api.payload['inputs']['project_id'], PROJECT)
        self.assertEqual(api.payload['ref'], 'main')

    def test_transient_github_errors_while_confirming_are_retried(self):
        api = GithubFixture(errors=2)
        receipt = arm(MANIFEST, SETUP, api=api, sleep=lambda seconds: None,
                      now=datetime(2026, 10, 26, tzinfo=timezone.utc))
        self.assertEqual(receipt['workflow_run_id'], 42)

    def test_unreadable_janitor_before_a_case_is_not_running(self):
        api = GithubFixture(errors=5)
        api.dispatched = True
        self.assertFalse(watch_running(RUN, 42, api=api, sleep=lambda seconds: None))
        api = GithubFixture(errors=1)
        api.dispatched = True
        self.assertTrue(watch_running(RUN, 42, api=api, sleep=lambda seconds: None))

    def test_invalid_identity_refuses_dispatch(self):
        api = GithubFixture()
        wrong = {'janitor': dict(SETUP['janitor'], service_account='other@example.com')}
        with self.assertRaisesRegex(ValueError, 'identity_missing'):
            arm(MANIFEST, wrong, api=api, now=datetime(2026, 10, 26, tzinfo=timezone.utc))
        self.assertEqual(api.calls, [])

    def test_watch_must_still_be_running_before_case(self):
        self.assertTrue(watch_running(RUN, 42, api=GithubFixture()))
        self.assertFalse(watch_running(RUN, 42, api=GithubFixture(step='completed')))
        self.assertFalse(watch_running('assess-different', 42, api=GithubFixture()))


if __name__ == '__main__':
    unittest.main()
