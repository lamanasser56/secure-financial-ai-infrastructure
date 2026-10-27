"""Waits poll the observable state and never run past the assessment deadline."""
from datetime import datetime, timedelta, timezone
import unittest

from cloud_wait import Waiter


DEADLINE = '2026-10-26T00:10:00+00:00'


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 26, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


class CloudWaitTest(unittest.TestCase):
    def test_poll_returns_the_first_visible_value_and_tolerates_unreadable_state(self):
        clock, answers = Clock(), iter([RuntimeError('not yet'), None, {'done': True}])

        def check():
            value = next(answers)
            if isinstance(value, Exception):
                raise value
            return value
        self.assertEqual(Waiter(DEADLINE, clock=clock, sleep=clock.sleep).poll(check, seconds=300, what='x'),
                         {'done': True})
        self.assertEqual(clock.now - datetime(2026, 10, 26, tzinfo=timezone.utc), timedelta(seconds=20))

    def test_waits_stop_at_the_assessment_deadline(self):
        clock = Clock()
        waiter = Waiter(DEADLINE, clock=clock, sleep=clock.sleep)
        with self.assertRaisesRegex(RuntimeError, 'wait_timeout:services'):
            waiter.poll(lambda: False, seconds=3600, what='services')
        self.assertEqual(clock.now, datetime.fromisoformat(DEADLINE))
        with self.assertRaisesRegex(RuntimeError, 'deadline_passed'):
            waiter.timeout(3600)

    def test_retry_keeps_the_last_error_and_value_errors_are_final(self):
        clock = Clock()
        waiter = Waiter(None, clock=clock, sleep=clock.sleep)
        with self.assertRaisesRegex(RuntimeError, 'retry_exhausted:binding') as raised:
            waiter.retry(lambda: (_ for _ in ()).throw(RuntimeError('iam')), seconds=60, what='binding')
        self.assertEqual(str(raised.exception.__cause__), 'iam')
        calls = []

        def final():
            calls.append(1)
            raise ValueError('identity_mismatch')
        with self.assertRaises(ValueError):
            waiter.retry(final, seconds=60, what='identity')
        self.assertEqual(len(calls), 1)

    def test_timeout_is_bounded_by_the_deadline(self):
        clock = Clock()
        self.assertEqual(Waiter(DEADLINE, clock=clock, sleep=clock.sleep).timeout(3600), 600)
        self.assertEqual(Waiter(None, clock=clock, sleep=clock.sleep).timeout(3600), 3600)


if __name__ == '__main__':
    unittest.main()
