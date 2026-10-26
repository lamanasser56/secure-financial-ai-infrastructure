"""Case order, independent cleanup, and both durable ledgers gate every probe."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from live_case_runner import CASE_ORDER, case_probes, run_all, run_case


class LiveCaseRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run_dir = Path(self.temp.name)
        evidence = self.run_dir / 'evidence'
        evidence.mkdir()
        self.manifest = {'run_id': 'assess-0123456789abcdef', 'source_commit': 'a' * 40,
                         'bundle_sha256': 'b' * 64, 'image_digests': {'app': 'app@sha256:' + 'c' * 64},
                         'cost_ceiling_usd': 50,
                         'deadline_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
        (evidence / 'bundle-applied.json').write_text(json.dumps({
            'run_id': self.manifest['run_id'], 'source_commit': self.manifest['source_commit'],
            'bundle_sha256': self.manifest['bundle_sha256'], 'verified_runtime_images': ['app']}))
        (evidence / 'janitor-armed.json').write_text(json.dumps({
            'run_id': self.manifest['run_id'], 'watch_step_in_progress': True,
            'workflow_run_id': 42}))
        self.calls = []

    def run_one(self, case='D02', checks=None, janitor=True, ledger=None):
        value = ledger or {'run_id': self.manifest['run_id'], 'completed_redactions': 0,
                           'sdk_attempts': 0, 'inflight': 0}
        return run_case(self.manifest, self.run_dir, case,
                        lambda: self.calls.append('probe') or (checks or {'checked': True}),
                        kubeconfig='/private/kubeconfig',
                        ledger_reader=lambda *_: self.calls.append('ledger') or value,
                        janitor_status=lambda run: self.calls.append('janitor') or janitor)

    def test_first_case_records_only_boolean_checks_and_both_ledgers(self):
        receipt = self.run_one(checks={'masked': True, 'stub_only': True})
        self.assertEqual(receipt['result'], 'PASS')
        self.assertEqual(self.calls, ['janitor', 'ledger', 'probe', 'ledger'])
        evidence = self.run_dir / 'evidence'
        self.assertTrue((evidence / 'case-D02-before-ledgers.json').is_file())
        self.assertTrue((evidence / 'case-D02-after-ledgers.json').is_file())
        self.assertEqual(json.loads((evidence / 'case-D02-result.json').read_text())['checks'],
                         {'masked': True, 'stub_only': True})

    def test_janitor_failure_and_out_of_order_refuse_probe(self):
        with self.assertRaisesRegex(RuntimeError, 'release_or_janitor_not_ready'):
            self.run_one(janitor=False)
        self.assertNotIn('probe', self.calls)
        self.calls.clear()
        with self.assertRaises(FileNotFoundError):
            self.run_one(case=CASE_ORDER[1])
        self.assertNotIn('probe', self.calls)

    def test_negative_check_blocks_next_case(self):
        with self.assertRaisesRegex(RuntimeError, 'case_fail'):
            self.run_one(checks={'denied': False})
        self.calls.clear()
        with self.assertRaisesRegex(RuntimeError, 'prior_case_not_passed'):
            self.run_one(case=CASE_ORDER[1])
        self.assertNotIn('probe', self.calls)

    def test_inflight_counter_refuses_case_before_probe(self):
        with self.assertRaisesRegex(RuntimeError, 'manual_stop_or_inflight'):
            self.run_one(ledger={'completed_redactions': 0, 'sdk_attempts': 0, 'inflight': 1})
        self.assertNotIn('probe', self.calls)

    def test_all_cases_are_bound_and_cleanup_is_required(self):
        probes = {case: lambda: {'checked': True} for case in CASE_ORDER}
        result = run_all(self.manifest, self.run_dir, kubeconfig='/private/kubeconfig',
                         probes=probes,
                         ledger_reader=lambda *_: {'run_id': self.manifest['run_id'],
                             'completed_redactions': 0, 'sdk_attempts': 0, 'inflight': 0},
                         janitor_status=lambda *_: True,
                         cleanup=lambda *_: {'result': 'PASS'})
        self.assertEqual(result['cases_passed'], 12)
        self.assertEqual(result['result'], 'PASS')
        self.assertTrue((self.run_dir / 'evidence/final-summary.json').exists())

    def test_current_source_bindings_cover_the_exact_twelve(self):
        self.assertEqual(set(case_probes(self.manifest, self.run_dir,
                                         '/private/kubeconfig')), set(CASE_ORDER))

    def test_failed_case_still_cleans_up(self):
        cleaned = []
        probes = {case: lambda: {'checked': True} for case in CASE_ORDER}
        probes['D02'] = lambda: {'checked': False}
        with self.assertRaisesRegex(RuntimeError, 'live_run_inconclusive'):
            run_all(self.manifest, self.run_dir, kubeconfig='/private/kubeconfig',
                    probes=probes,
                    ledger_reader=lambda *_: {'run_id': self.manifest['run_id'],
                        'completed_redactions': 0, 'sdk_attempts': 0, 'inflight': 0},
                    janitor_status=lambda *_: True,
                    cleanup=lambda *_: cleaned.append(True) or {'result': 'PASS'})
        self.assertEqual(cleaned, [True])


if __name__ == '__main__':
    unittest.main()
