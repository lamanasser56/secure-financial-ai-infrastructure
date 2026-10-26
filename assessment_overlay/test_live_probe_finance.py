"""Finance probes emit only boolean summaries from the current frontdoor Pod."""
import unittest

from live_probe_finance import SCRIPTS, probe
from live_probe_kube import one_pod, python_probe


class FinanceProbeTest(unittest.TestCase):
    def test_source_scripts_compile_and_bind_to_current_frontdoor(self):
        self.assertEqual(set(SCRIPTS), {'D05', 'D06', 'D07'})
        calls = []
        for case, script in SCRIPTS.items():
            compile(script, case, 'exec')
            result = probe(case, '/private/kube', executable='/pin/kubectl',
                           pod=lambda *args, **kw: calls.append(('pod', args, kw)) or 'frontdoor-abc',
                           execute=lambda *args, **kw: calls.append(('exec', args, kw)) or {'denied': True})
            self.assertEqual(result, {'denied': True})
        self.assertEqual(len(calls), 6)
        self.assertTrue(all(call[1][1] == 'apps' for call in calls))
        self.assertTrue(all(call[2]['executable'] == '/pin/kubectl' for call in calls))

    def test_pod_selection_and_summary_refuse_ambiguous_or_content_results(self):
        fixture = {'items': [{'metadata': {'name': 'frontdoor-abc'}, 'status': {'phase': 'Running'}}]}
        def fake(command, *, input=None):
            if 'get' in command:
                import json
                return json.dumps(fixture)
            return '{"masked": true, "denied": true}'
        name = one_pod('/private/kube', 'apps', 'app.kubernetes.io/name=financial-frontdoor', run=fake)
        self.assertEqual(name, 'frontdoor-abc')
        self.assertEqual(python_probe('/private/kube', 'apps', name, 'print(1)', run=fake),
                         {'masked': True, 'denied': True})
        fixture['items'].append(fixture['items'][0])
        with self.assertRaisesRegex(RuntimeError, 'exactly_one_running_pod'):
            one_pod('/private/kube', 'apps', 'name=frontdoor', run=fake)
        with self.assertRaisesRegex(RuntimeError, 'probe_summary_invalid'):
            python_probe('/private/kube', 'apps', name, 'print(1)',
                         run=lambda *args, **kw: '{"raw_input": "alice@example.com"}')


if __name__ == '__main__':
    unittest.main()
