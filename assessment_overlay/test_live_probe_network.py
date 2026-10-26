"""The network probe covers every current allowed/denied source-destination pair."""
import unittest

from live_probe_network import MATRIX, SCRIPT, probe_k01


class NetworkProbeTest(unittest.TestCase):
    def test_full_current_matrix_runs_inside_source_pods(self):
        self.assertEqual(sum(len(spec[2]) for spec in MATRIX.values()), 11)
        calls = []
        def pod(kubeconfig, namespace, selector, *, executable):
            calls.append((namespace, selector))
            return namespace + '-pod'
        def execute(kubeconfig, namespace, name, script, *, executable):
            compile(script, namespace, 'exec')
            targets = MATRIX[next(label for label, item in MATRIX.items() if item[0] == namespace
                                  or (namespace == 'platform' and label == 'boundary'))][2]
            return {target[0]: True for target in targets}
        checks = probe_k01('/private/kube', pod=pod, execute=execute)
        self.assertEqual(len(checks), 11)
        self.assertTrue(all(checks.values()))
        self.assertEqual(len(calls), 4)
        self.assertNotIn('kubectl', SCRIPT)

    def test_missing_destination_refuses_pass(self):
        with self.assertRaisesRegex(RuntimeError, 'network_matrix_incomplete'):
            probe_k01('/private/kube', pod=lambda *a, **kw: 'pod',
                      execute=lambda *a, **kw: {'only_one': True})


if __name__ == '__main__':
    unittest.main()
