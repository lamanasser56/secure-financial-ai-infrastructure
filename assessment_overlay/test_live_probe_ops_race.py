"""O03 targets only the zero-replica disposable Deployment and exact-object races."""
import json
from pathlib import Path
import tempfile
import unittest

from live_probe_ops_race import EXECUTE, SIGN, SNAPSHOT, bound_run, proposal


class OpsRaceProbeTest(unittest.TestCase):
    def test_remote_scripts_compile_and_bind_exact_denials(self):
        for name, source in (('snapshot', SNAPSHOT), ('sign', SIGN), ('execute', EXECUTE)):
            compile(source, name, 'exec')
        self.assertIn("'TARGET_REPLACED'", EXECUTE)
        self.assertIn("'OBJECT_CHANGED'", EXECUTE)
        self.assertIn("Path('/secrets/app/app.json')", SIGN)

    def test_proposal_is_bound_to_observed_uid_version_and_digest(self):
        item = proposal({'finding': 'HEALTHY', 'uid': 'uid-a',
                         'resource_version': '42', 'evidence_digest': 'a' * 64})
        self.assertEqual(item['target'], 'apps.fault-demo')
        self.assertEqual(item['action'], 'restart')
        self.assertEqual(item['uid'], 'uid-a')
        self.assertEqual(item['resource_version'], '42')
        with self.assertRaises(RuntimeError):
            proposal({'finding': 'PENDING', 'uid': 'uid-a',
                      'resource_version': '42', 'evidence_digest': 'a' * 64})

    def test_original_or_unbound_cluster_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'kube').mkdir()
            (root / 'evidence').mkdir()
            (root / 'evidence/bundle-applied.json').write_text('{}')
            manifest = {'disposable_project_id': 'sfai-assess-abcdefgh'}
            (root / 'initial-manifest.json').write_text(json.dumps(manifest))
            bound_run(manifest, root, root / 'kube/kubeconfig')
            with self.assertRaisesRegex(RuntimeError, 'disposable_run_binding_required'):
                bound_run(manifest, root, root / 'other-kubeconfig')
            with self.assertRaisesRegex(RuntimeError, 'disposable_run_binding_required'):
                bound_run({'disposable_project_id': 'original-project'}, root,
                          root / 'kube/kubeconfig')


if __name__ == '__main__':
    unittest.main()
