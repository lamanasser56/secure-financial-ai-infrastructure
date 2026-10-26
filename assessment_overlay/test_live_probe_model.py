"""D02 checks real redaction and one dispatch without retaining input text."""
import unittest

from live_probe_model import STATS, WORKER, probe, stub_stats


class ModelProbeTest(unittest.TestCase):
    def test_scripts_compile_and_case_requires_one_clean_stub_dispatch(self):
        compile(STATS, 'stub-stats', 'exec')
        compile(WORKER, 'd02-worker', 'exec')
        counts = iter(({'requests': 0, 'raw_canary_seen': False},
                       {'requests': 1, 'raw_canary_seen': False}))
        calls = []
        checks = probe('/private/kube', executable='/pin/kubectl',
                       pod=lambda *a, **kw: calls.append((a, kw)) or 'exact-pod',
                       execute=lambda *a, **kw: {'email_masked': True, 'phone_masked': True,
                                                   'provider_direct_denied': True,
                                                   'gateway_private_response': True},
                       stats=lambda *a, **kw: next(counts))
        self.assertTrue(all(checks.values()))
        self.assertEqual([call[0][1] for call in calls], ['assess-probes', 'agent-financial'])
        self.assertEqual([call[0][2] for call in calls],
                         ['assessment.role=provider-stub', 'agent-platform/user-slot=u1'])

    def test_bad_stub_stats_cannot_pass(self):
        with self.assertRaisesRegex(RuntimeError, 'stub_stats_invalid'):
            stub_stats('/private/kube', 'stub', run=lambda *a, **kw: '{"requests":1,"raw_canary_seen":"false"}')


if __name__ == '__main__':
    unittest.main()
