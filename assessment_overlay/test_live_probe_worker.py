"""D04 live checks avoid presenting a revoked token as cross-user evidence."""
import unittest

from live_probe_worker import FRONTDOOR, WORKER, probe_d04


class WorkerProbeTest(unittest.TestCase):
    def test_current_frontdoor_and_worker_probes_compile(self):
        compile(FRONTDOOR, 'd04-frontdoor', 'exec')
        compile(WORKER, 'd04-worker', 'exec')
        calls = []
        def execute(kubeconfig, namespace, name, script, *, executable):
            calls.append(namespace)
            return {'frontdoor_denial': True} if namespace == 'apps' else {'worker_isolation': True}
        result = probe_d04('/private/kube', pod=lambda *a, **kw: a[1] + '-pod', execute=execute)
        self.assertTrue(all(result.values()))
        self.assertEqual(calls, ['apps', 'agent-financial'])
        self.assertIn('extra_user_id_rejected', FRONTDOOR)
        self.assertIn('direct_database_denied', WORKER)


if __name__ == '__main__':
    unittest.main()
