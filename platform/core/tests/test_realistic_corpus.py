"""The synthetic Saudi/bilingual corpus (platform/core/tests/corpus/) through the client redaction layers, offline.

Realistic-data review 2026-10 (RD-01 to RD-04, RD-08, RD-09). Every value the platform says it covers must be masked
before the redactor, in every prompt shape a call site builds: the raw text, the Financial Agent's
json.dumps(ensure_ascii=False) prompt with the value at the start of a pasted line, and the ops explainer's
json.dumps(ensure_ascii=True) with \\uXXXX-escaped Arabic text and digits. The fake redactor finds nothing (the worst
case); what the real Sensitive Data Protection policy adds is checked live, categories only.
"""
import json
from pathlib import Path
import re
import sys
import unicodedata
import unittest

from agent_platform.identifiers import identifier_spans, mask
from runtime.phase3.deterministic_email import DeterministicEmailRedactor
import test_identifiers

CORPUS_DIR = Path(__file__).parent / 'corpus'
CORPUS = json.loads((CORPUS_DIR / 'saudi_bilingual_corpus.json').read_text(encoding='utf-8'))
DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
SHAPES = {
    'raw': lambda text: text,
    'financial prompt, value at a line start': lambda text: json.dumps(
        {'question': 'Please check this:\n' + text, 'history': [], 'observations': []}, ensure_ascii=False),
    'ops explainer, ensure_ascii': lambda text: json.dumps({'evidence': {'message': '\n' + text}}, sort_keys=True),
}


def normalized(text):
    """Escapes decoded, format characters, separators and brackets removed, digits as ASCII, lower case: a value
    counts as leaked even if only its digits survive in another script or with other separators."""
    text = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return re.sub(r'[\s\-–.()+   ‑＠@]', '', text).translate(DIGITS).lower()


def sent_to_redactor(text):
    """What leaves for the redactor: the email layer, then the platform client (structured identifiers), as wired in
    the front door and the Financial Agent."""
    seen = []
    DeterministicEmailRedactor(test_identifiers.echo_client(seen)).redact(text)
    return seen[0]


class Corpus(unittest.TestCase):
    def test_the_committed_corpus_is_what_the_generator_writes(self):
        sys.path.insert(0, str(CORPUS_DIR))
        import make_corpus
        self.assertEqual(make_corpus.build(), CORPUS)

    def test_synthetic_domains_only_and_never_gov_sa(self):
        suffixes = ('.sa', '.com.sa', '.org.sa', '.edu.sa', '.net.sa')
        self.assertTrue(all(d.endswith(suffixes) and '-fixture' in d for d in CORPUS['domains']))
        self.assertNotIn('.gov.sa', json.dumps({k: v for k, v in CORPUS.items() if k != '_comment'}))

    def test_every_covered_value_is_masked_in_every_prompt_shape(self):
        covered = [item for item in CORPUS['items'] if item['covered']]
        self.assertGreaterEqual(len(covered), 180)
        for item in covered:
            for shape, build in SHAPES.items():
                with self.subTest(item=item['id'], shape=shape):
                    sent = normalized(sent_to_redactor(build(item['text'])))
                    for value in item['values']:
                        self.assertNotIn(normalized(value), sent)

    def test_every_value_in_the_pasted_documents_is_masked(self):
        for document in CORPUS['documents']:
            for shape, build in SHAPES.items():
                with self.subTest(document=document['id'], shape=shape):
                    sent = normalized(sent_to_redactor(build(document['text'])))
                    for value in document['values']:
                        self.assertNotIn(normalized(value), sent)

    def test_masking_keeps_json_prompts_valid_json(self):
        for text in [item['text'] for item in CORPUS['items']] + [d['text'] for d in CORPUS['documents']]:
            for shape in ('financial prompt, value at a line start', 'ops explainer, ensure_ascii'):
                prompt = SHAPES[shape](text)
                with self.subTest(text=text[:40], shape=shape):
                    json.loads(mask(prompt, identifier_spans(prompt)))

    def test_amounts_dates_and_injection_text_are_left_alone(self):
        for text in CORPUS['injection']['merchants'] + [g['answer'] for g in CORPUS['grounding']]:
            with self.subTest(text=text):
                self.assertEqual(identifier_spans(text), [])
                self.assertEqual(identifier_spans(json.dumps({'q': '\n' + text})), [])


if __name__ == '__main__':
    unittest.main()
