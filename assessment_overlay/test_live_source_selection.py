"""Only the committed harness may differ from S; a dirty checkout never selects S."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from live_session import session_manifest
from render_live_bundle import RELEASE_LOCK, assert_harness_unchanged, harness_record, selected_source


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


class Repository:
    """A throwaway repository whose first commit plays the role of S."""

    def __init__(self, root):
        self.root = Path(root)
        git(self.root, 'init', '-q')
        git(self.root, 'config', 'user.email', 'fixture@example.invalid')
        git(self.root, 'config', 'user.name', 'fixture')
        git(self.root, 'config', 'commit.gpgsign', 'false')
        self.write('platform/product.py', 'PRODUCT = 1\n')
        self.write('assessment_overlay/probe.py', 'PROBE = 1\n')
        self.write(RELEASE_LOCK, '{}\n')
        self.write('.gitignore', '.cache/\n')
        self.source = self.commit('S')

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self, message):
        git(self.root, 'add', '-A')
        git(self.root, 'commit', '-q', '--allow-empty', '-m', message)
        return git(self.root, 'rev-parse', 'HEAD')

    def lock(self):
        return {'schema_version': 2, 'runtime_contract': 'trusted-boundaries-v2',
                'source_commit': self.source, 'images': {}}


class SourceSelectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Repository(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def select(self):
        return selected_source(self.repo.lock(), self.repo.root)

    def test_exact_source_is_selected_with_an_empty_harness_diff(self):
        self.assertEqual(self.select(), self.repo.source)
        record, diff = harness_record(self.repo.source, self.repo.root)
        self.assertEqual(record['harness_commit'], self.repo.source)
        self.assertEqual(record['harness_changed_files'], [])
        self.assertEqual(diff, '')

    def test_changed_product_file_fails(self):
        self.repo.write('platform/product.py', 'PRODUCT = 2\n')
        self.repo.commit('product change')
        with self.assertRaisesRegex(ValueError, 'differs from qualified release'):
            self.select()

    def test_changed_harness_passes_and_is_recorded(self):
        self.repo.write('assessment_overlay/probe.py', 'PROBE = 2\n')
        self.repo.write('assessment_overlay/cloud_wait.py', 'WAIT = 1\n')
        head = self.repo.commit('harness change')
        self.assertEqual(self.select(), self.repo.source)
        record, diff = harness_record(self.repo.source, self.repo.root)
        self.assertEqual(record['harness_commit'], head)
        self.assertEqual(record['harness_changed_files'],
                         ['assessment_overlay/cloud_wait.py', 'assessment_overlay/probe.py'])
        self.assertIn('+PROBE = 2', diff)
        self.assertEqual(record['harness_diff_sha256'], hashlib.sha256(diff.encode()).hexdigest())
        manifest = session_manifest('sfai-assess-fixture01', self.repo.lock(), self.repo.root / RELEASE_LOCK,
                                    'assess-0123456789abcdef', datetime(2026, 10, 27, tzinfo=timezone.utc),
                                    root=self.repo.root)
        self.assertEqual(manifest['source_commit'], self.repo.source)
        self.assertEqual(manifest['harness_commit'], head)
        self.assertEqual(manifest['harness_diff_sha256'], record['harness_diff_sha256'])

    def test_release_lock_and_evidence_may_change(self):
        self.repo.write(RELEASE_LOCK, json.dumps({'source_commit': self.repo.source}))
        self.repo.write('docs/evidence/release.json', '{}\n')
        self.repo.commit('lock and evidence')
        self.assertEqual(self.select(), self.repo.source)

    def test_moving_product_code_into_the_harness_fails(self):
        git(self.repo.root, 'mv', 'platform/product.py', 'assessment_overlay/product.py')
        self.repo.commit('move')
        with self.assertRaisesRegex(ValueError, 'differs from qualified release'):
            self.select()

    def test_dirty_working_tree_fails(self):
        for change in ('unstaged', 'staged', 'untracked harness', 'untracked product', 'hidden'):
            with self.subTest(change=change):
                repo = Repository(tempfile.mkdtemp(dir=self.temp.name))
                if change == 'unstaged':
                    repo.write('assessment_overlay/probe.py', 'PROBE = 3\n')
                elif change == 'staged':
                    repo.write('platform/product.py', 'PRODUCT = 3\n')
                    git(repo.root, 'add', 'platform/product.py')
                elif change == 'untracked harness':
                    repo.write('assessment_overlay/local_patch.py', 'PATCH = 1\n')
                elif change == 'untracked product':
                    repo.write('platform/extra.py', 'EXTRA = 1\n')
                else:
                    git(repo.root, 'update-index', '--assume-unchanged', 'assessment_overlay/probe.py')
                    repo.write('assessment_overlay/probe.py', 'PROBE = 4\n')
                with self.assertRaisesRegex(ValueError, 'uncommitted or untracked'):
                    selected_source(repo.lock(), repo.root)

    def test_ignored_cache_does_not_make_the_checkout_dirty(self):
        self.repo.write('.cache/platform-tools/kubectl', 'binary\n')
        self.assertEqual(self.select(), self.repo.source)

    def test_operator_steps_refuse_a_checkout_changed_after_the_session(self):
        record, _ = harness_record(self.repo.source, self.repo.root)
        assert_harness_unchanged(record, self.repo.root)
        self.repo.write('assessment_overlay/probe.py', 'PROBE = 5\n')
        with self.assertRaisesRegex(SystemExit, 'harness_checkout_changed'):
            assert_harness_unchanged(record, self.repo.root)
        self.repo.commit('later harness commit')
        with self.assertRaisesRegex(SystemExit, 'harness_checkout_changed'):
            assert_harness_unchanged(record, self.repo.root)


if __name__ == '__main__':
    unittest.main()
