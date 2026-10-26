"""R01 uses only private synthetic users and returns boolean session findings."""
import json
from pathlib import Path
import tempfile
import unittest

from live_probe_session import probe_r01


class SessionProbeTest(unittest.TestCase):
    def test_private_users_both_scopes_and_csrf_probe_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'financial-users.json').write_text(json.dumps({
                'lama': 'synthetic-one', 'sara': 'synthetic-two', 'omar': 'synthetic-three'}))
            def execute(kubeconfig, namespace, name, script, *, executable):
                compile(script, 'r01', 'exec')
                self.assertIn("for username in ('lama','sara')", script)
                self.assertIn('tampered_cookie_denied', script)
                self.assertNotIn('__USERS__', script)
                return {'sessions_scoped': True}
            self.assertEqual(probe_r01('/private/kube', directory, 'assess-0123456789abcdef',
                                       pod=lambda *a, **kw: 'frontdoor-pod', execute=execute),
                             {'sessions_scoped': True})

    def test_missing_synthetic_credentials_refuse_pod_access(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'financial-users.json').write_text(json.dumps({'lama': 'only-one'}))
            with self.assertRaisesRegex(ValueError, 'credentials_invalid'):
                probe_r01('/private/kube', directory, 'assess-0123456789abcdef',
                          pod=lambda *a, **kw: self.fail('pod access must not start'))


if __name__ == '__main__':
    unittest.main()
