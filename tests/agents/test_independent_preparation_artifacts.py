"""Prevent stale candidate evidence or an implied authority promotion."""

import hashlib
from pathlib import Path
import unittest
from tests.qualification_history import HISTORICAL_LOCK_SHA256, HISTORICAL_SOURCE_SHA256, historical_input

ROOT = Path(__file__).resolve().parents[2]


class PreparationEvidenceTests(unittest.TestCase):

    def test_current_locks_are_not_live_qualified_per_claude_handoff_final(self):
        """CLAUDE_HANDOFF_FINAL.md (rc1-live-followup:bed7b0e) requires fresh live qualification."""
        for path, historical_hash in (HISTORICAL_LOCK_SHA256 | HISTORICAL_SOURCE_SHA256).items():
            with self.subTest(lock=path):
                self.assertEqual(
                    hashlib.sha256(historical_input(ROOT, path, historical_hash).read_bytes()).hexdigest(),
                    historical_hash,
                )
                self.assertNotEqual(
                    hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                    historical_hash,
                    f"{path} needs a new live qualification record before it can be claimed qualified",
                )
