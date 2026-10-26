"""Current human masking reference follows the executable category authority."""
from pathlib import Path
import re
import unittest

from agent_platform.masking_scope import scope

ROOT = Path(__file__).resolve().parents[3]


class CurrentDocs(unittest.TestCase):
    def test_reference_lists_exact_current_types_and_the_unsupported_boundary(self):
        text = (ROOT / 'docs/security/masking-scope.md').read_text()
        listed = set(re.findall(r'^\| `([A-Z_]+)` \|', text, re.MULTILINE))
        current = scope()
        self.assertEqual(listed, {item['code'] for item in current['supported']})
        self.assertIn('Person names and passport numbers are not masked.', text)
        self.assertIn(current['limits'], text)

    def test_arabic_guide_reference_lists_the_same_supported_types(self):
        text = (ROOT / 'docs/platform/guide.ar.md').read_text()
        listed = set(re.findall(r'`([A-Z_]+)`', text))
        self.assertEqual(listed, {item['code'] for item in scope()['supported']})
        self.assertIn('لا تُخفى أسماء الأشخاص أو أرقام جوازات السفر', text)
