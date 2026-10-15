"""Redactor: a provider channel left idle goes stale; the service rebuilds the client and still fails closed."""
import unittest

from agent_platform.programs import redactor_server
from agent_platform.programs.redactor_server import Budget

STALE_AFTER = 600  # a channel idle this long is dropped silently by the network path


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeProvider:
    """One adapter == one channel. A call on a channel idle for STALE_AFTER seconds waits out the deadline and fails."""

    def __init__(self, clock, window_budget):
        self.clock, self.window_budget = clock, window_budget
        self.last_rpc = clock()
        self.operation_counts = {'inspect_attempted': 0, 'deidentify_attempted': 0}

    def redact(self, text):
        self.operation_counts['inspect_attempted'] += 1  # one redaction = one inspect + one deidentify
        self.operation_counts['deidentify_attempted'] += 1
        self.window_budget['used'] += 2
        if self.clock() - self.last_rpc >= STALE_AFTER:
            raise TimeoutError('RPC_TIMEOUT')  # the adapter's DeadlineExceeded -> fail closed
        self.last_rpc = self.clock()
        return text


def make(clock, **options):
    built = []

    def factory(window):
        built.append(FakeProvider(clock, window))
        return built[-1]
    return Budget(factory, lambda: {'used': 0}, clock=clock, **options), built


class StaleChannel(unittest.TestCase):
    def test_a_long_lived_client_fails_after_the_idle_gap(self):
        clock = Clock()
        budget, _ = make(clock, idle_seconds=10 ** 9)  # recreation disabled: the behaviour before the fix
        budget.current().redact('first')
        clock.now += 11 * 60
        with self.assertRaises(TimeoutError):
            budget.current().redact('after idle')

    def test_the_client_is_rebuilt_after_idle_so_the_first_call_succeeds(self):
        clock = Clock()
        budget, built = make(clock)
        budget.current().redact('first')
        clock.now += 11 * 60
        self.assertEqual(budget.current().redact('after idle'), 'after idle')
        self.assertEqual(len(built), 2)

    def test_busy_traffic_keeps_one_client(self):
        clock = Clock()
        budget, built = make(clock)
        for _ in range(20):
            clock.now += redactor_server.IDLE_SECONDS - 1
            budget.current().redact('x')
        self.assertEqual(len(built), 1)

    def test_rebuild_does_not_renew_the_window_attempt_budget(self):
        clock = Clock()
        budget, built = make(clock)
        budget.current().redact('a')
        clock.now += redactor_server.IDLE_SECONDS
        budget.current().redact('b')
        self.assertIs(built[0].window_budget, built[1].window_budget)
        self.assertEqual(built[1].window_budget['used'], 4)

    def test_rebuild_does_not_reset_the_daily_ceiling(self):
        clock = Clock()
        budget, built = make(clock, idle_seconds=1)
        for _ in range(redactor_server.DAILY_OPERATIONS // 2):
            budget.current().redact('x')
            clock.now += 1  # every call lands on a fresh client, inside one window and one day
        self.assertGreater(len(built), 800)
        with self.assertRaisesRegex(RuntimeError, 'daily budget'):
            budget.current()

    def test_failure_is_still_raised_not_swallowed(self):
        clock = Clock()
        budget, built = make(clock)
        provider = budget.current()
        provider.redact = lambda text: (_ for _ in ()).throw(RuntimeError('provider down'))
        with self.assertRaises(RuntimeError):
            budget.current().redact('x')
        self.assertEqual(len(built), 1)

    def test_the_provider_deadline_is_unchanged(self):
        from runtime.phase3 import google_sdp_adapter
        self.assertEqual((google_sdp_adapter.RPC_TIMEOUT_SECONDS, google_sdp_adapter.OVERALL_TIMEOUT_SECONDS), (3, 8))


if __name__ == '__main__':
    unittest.main()
