"""K05 checks exact Workload Identity inventory and avoids a DLP content call."""
import json
import unittest

from live_probe_identity import REMOTE, probe_k05, workload_identity_inventory


class IdentityProbeTest(unittest.TestCase):
    def test_exact_binding_and_three_pod_matrix(self):
        project = 'sfai-assess-fixture01'
        expected = 'google-sdp-runtime@' + project + '.iam.gserviceaccount.com'
        items = [{'metadata': {'namespace': 'platform', 'name': 'redactor',
                                'annotations': {'iam.gke.io/gcp-service-account': expected}}},
                 {'metadata': {'namespace': 'apps', 'name': 'app'}}]
        def read(*args):
            return json.dumps({'items': items})
        self.assertTrue(workload_identity_inventory('/private/kube', project, run=read))
        items[1]['metadata']['annotations'] = {'iam.gke.io/gcp-service-account': expected}
        self.assertFalse(workload_identity_inventory('/private/kube', project, run=read))
        responses = iter(({'expected_identity': True, 'no_identity': False, 'dlp_tcp': True},
                          {'expected_identity': False, 'no_identity': True, 'dlp_tcp': False},
                          {'expected_identity': False, 'no_identity': True, 'dlp_tcp': False}))
        result = probe_k05('/private/kube', project,
                           pod=lambda *a, **kw: a[1] + '-pod',
                           execute=lambda *a, **kw: next(responses),
                           inventory=lambda *a, **kw: True)
        self.assertTrue(all(result.values()))
        compile(REMOTE.replace('__EXPECTED_GSA__', expected), 'k05', 'exec')
        self.assertNotIn('POST', REMOTE)


if __name__ == '__main__':
    unittest.main()
