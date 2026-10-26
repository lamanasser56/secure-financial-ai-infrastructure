"""Offline safety checks for a fresh assessment session."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from live_session import HARD_LIMITS, ROOT, private_path, session_manifest


class LiveSessionTest(unittest.TestCase):
    def lock(self):
        source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        return {'schema_version': 2, 'runtime_contract': 'trusted-boundaries-v2',
                'source_commit': source, 'images': {'redactor': 'redactor@sha256:' + 'a' * 64}}

    def test_current_source_and_original_case_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'images.json'
            lock = self.lock()
            path.write_text(json.dumps(lock))
            manifest = session_manifest('sfai-assess-fixture01', lock, path, 'assess-0123456789abcdef',
                                        datetime(2026, 10, 26, tzinfo=timezone.utc))
        self.assertEqual(manifest['source_commit'], lock['source_commit'])
        self.assertEqual(manifest['external_llm_calls_allowed'], 0)
        self.assertEqual(manifest['hard_limits'], list(HARD_LIMITS))
        self.assertEqual(manifest['manual_stop'], [12, 40])
        self.assertEqual(manifest['planned_limits'], [8, 19])
        self.assertEqual(manifest['cost_ceiling_usd'], 50)
        self.assertEqual(len(manifest['case_allocations']), 12)
        self.assertIn('billing_unlinked', manifest['cleanup_required'])

    def test_original_project_or_checkout_output_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'images.json'
            lock = self.lock()
            path.write_text(json.dumps(lock))
            with self.assertRaisesRegex(ValueError, 'disposable assessment project'):
                session_manifest('fixture-original', lock, path, 'assess-0123456789abcdef',
                                 datetime.now(timezone.utc))
        with self.assertRaisesRegex(ValueError, 'outside the checkout'):
            private_path(ROOT / '.cache/assessment-private')


if __name__ == '__main__':
    unittest.main()
