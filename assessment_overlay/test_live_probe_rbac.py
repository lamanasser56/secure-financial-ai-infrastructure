"""K02's denial requests use only the projected observer token and dry-run writes."""
import unittest

from live_probe_rbac import K02, K03, probe_k02, probe_k03, restricted_psa


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

    def test_executor_probe_uses_dry_run_for_all_patches(self):
        compile(K03, 'k03', 'exec')
        self.assertEqual(K03.count("path + '?dryRun=All'"), 3)
        calls = []
        result = probe_k03('/private/kube',
                           pod=lambda *a, **kw: calls.append(a) or 'ops-executor-abc',
                           execute=lambda *a, **kw: {'allowed_restart_dry_run': True,
                                                        'template_image_change_denied': True},
                           psa=lambda *a, **kw: True)
        self.assertTrue(all(result.values()))
        self.assertTrue(result['restricted_psa_denied_privileged_pod'])
        self.assertEqual(calls[0][1:], ('ops', 'app.kubernetes.io/name=ops-executor'))

    def test_restricted_psa_requires_admission_reason(self):
        class Result:
            returncode = 1
            stdout = ''
            stderr = 'pods "assessment-psa-denied" is forbidden: violates PodSecurity "restricted:latest"'
        self.assertTrue(restricted_psa('/private/kube', run=lambda *a, **kw: Result()))
        Result.stderr = 'pods is forbidden by RBAC'
        self.assertFalse(restricted_psa('/private/kube', run=lambda *a, **kw: Result()))


if __name__ == '__main__':
    unittest.main()
