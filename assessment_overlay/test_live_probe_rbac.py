"""K02's denial requests use only the projected observer token and dry-run writes."""
import unittest

from live_probe_rbac import K02, probe_k02


class RbacProbeTest(unittest.TestCase):
    def test_current_pods_and_explicit_dry_run(self):
        seen = []
        def pod(kubeconfig, namespace, selector, *, executable):
            seen.append((namespace, selector))
            return 'ops-agent-abc' if namespace == 'ops' else 'app-abc'
        def execute(kubeconfig, namespace, name, script, *, executable):
            compile(script, 'k02', 'exec')
            self.assertIn('/pods/app-abc/exec', script)
            self.assertEqual(script.count('dryRun=All'), 2)
            return {'patch_denied': True, 'secret_read_denied': True}
        result = probe_k02('/private/kube', pod=pod, execute=execute)
        self.assertTrue(all(result.values()))
        self.assertEqual(seen, [('ops', 'app.kubernetes.io/name=ops-agent'),
                                ('apps', 'app.kubernetes.io/name=app')])
        self.assertIn("Path('/var/run/secrets/kubernetes.io/serviceaccount')", K02)


if __name__ == '__main__':
    unittest.main()
