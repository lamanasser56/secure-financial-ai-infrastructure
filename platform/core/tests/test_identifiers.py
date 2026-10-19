"""Structured identifiers are masked before the redactor and the model on every path (redaction gap of 2026-10-17).

The fake redactor here echoes its input and finds nothing: the worst case, where the provider policy matches nothing. Even
then no phone, IBAN or VAT number from the pasted invoice may reach the redactor or the gateway. What the real provider
adds on top (its own EMAIL_ADDRESS and context patterns) needs the live DLP check and is not asserted here.
"""
import json
from pathlib import Path
import unittest

from agent_platform.identifiers import identifier_spans, mask
from agent_platform.redaction import RedactorClient
from runtime.phase3.deterministic_email import DeterministicEmailRedactor
from runtime.phase3.trusted_runtime import ControlFailure

CASES = json.loads((Path(__file__).parent / 'identifier_cases.json').read_text(encoding='utf-8'))
INVOICE, VALUES, EMAILS = CASES['invoice'], CASES['invoice_values'], CASES['invoice_emails']


class Response:
    def __init__(self, body):
        self.status, self._body = 200, json.dumps(body).encode()

    def read(self, limit=None):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def echo_client(seen, reply=None):
    """The production client against a redactor that finds nothing (or answers `reply`)."""
    def opener(request, timeout=None):
        text = json.loads(request.data)['text']
        seen.append(text)
        return Response(reply if reply is not None else {'text': text, 'categories': []})
    return RedactorClient('http://redactor.platform.svc.cluster.local:4003', 'k' * 64, opener=opener)


def pairs(text):
    return [[category, text[start:end]] for start, end, category in identifier_spans(text)]


class Detector(unittest.TestCase):
    def test_shared_cases_parity_with_the_guide(self):
        for case in CASES['cases']:
            with self.subTest(text=case['text'][:60]):
                self.assertEqual(pairs(case['text']), case['expected'])

    def test_every_prompt_shape_used_by_a_call_site(self):
        shapes = {
            'raw question (answer re-redaction, history, guide steps)': INVOICE,
            'financial agent prompt, json.dumps(ensure_ascii=False)': json.dumps(
                {'question': INVOICE, 'history': [{'question': 'x\n' + INVOICE}], 'observations': []}, ensure_ascii=False),
            'front-door core, compact separators': json.dumps({'message': INVOICE}, ensure_ascii=False, separators=(',', ':')),
            'ops explainer, json.dumps(sort_keys=True)': json.dumps({'evidence': {'message': INVOICE}}, sort_keys=True),
        }
        for name, text in shapes.items():
            with self.subTest(shape=name):
                masked = mask(text, identifier_spans(text))
                for value in VALUES:
                    self.assertNotIn(value, masked)

    def test_other_records_ids_are_not_national_ids(self):
        """Owner review of #118: the bare "ID" label masked "Order ID 1234567890" and "Transaction ID: 1029384756"."""
        for text in ('Order ID 1234567890', 'Transaction ID: 1029384756', 'Order ID is 2123456789', 'Booking ID: 2123456789'):
            for shaped in (text, json.dumps({'question': 'x\n' + text}, ensure_ascii=False), json.dumps({'m': text})):
                with self.subTest(text=shaped):
                    self.assertEqual(identifier_spans(shaped), [])
        self.assertEqual(pairs('ID: 1073059188'), [['SAUDI_NATIONAL_ID', '1073059188']])

    def test_iqama_and_generic_id_labels_take_the_category_from_the_first_digit(self):
        """Lama's review of #118: these reached the model unmasked."""
        expected = {'Iqama ID: 2123456789': 'SAUDI_RESIDENT_ID', 'Iqama ID 2123456789': 'SAUDI_RESIDENT_ID',
                    'ID: 2123456789': 'SAUDI_RESIDENT_ID', 'my ID is 1073059188': 'SAUDI_NATIONAL_ID',
                    'Iqama Number: 2123456789': 'SAUDI_RESIDENT_ID', 'Resident ID No. 2123456789': 'SAUDI_RESIDENT_ID',
                    'Residence ID 2123456789': 'SAUDI_RESIDENT_ID', 'رقم إقامتي 2123456789': 'SAUDI_RESIDENT_ID',
                    'ID No 1073059188': 'SAUDI_NATIONAL_ID', 'ID Number 2123456789': 'SAUDI_RESIDENT_ID',
                    'Saudi ID 1073059188': 'SAUDI_NATIONAL_ID', 'ID is 2123456789': 'SAUDI_RESIDENT_ID',
                    'رقمي 2123456789': 'SAUDI_RESIDENT_ID', 'هويتي رقمها 1073059188': 'SAUDI_NATIONAL_ID'}
        for text, category in expected.items():
            for shaped in (text, json.dumps({'question': 'x\n' + text}, ensure_ascii=False), json.dumps({'m': '\n' + text})):
                with self.subTest(text=shaped):
                    self.assertEqual([c for _, _, c in identifier_spans(shaped)], [category])
                    self.assertNotIn(text[-10:], mask(shaped, identifier_spans(shaped)))

    def test_passports_are_a_documented_gap_not_mislabelled(self):
        """No qualified passport category exists (SUPPORTED_ENTITIES is hash-bound): not masked as anything else."""
        for text in ('Passport ID: A12345678', 'Passport No. AB1234567', 'رقم الجواز: A12345678'):
            self.assertEqual(identifier_spans(text), [])

    def test_amounts_dates_and_references_are_untouched(self):
        text = 'You spent 830.49 SAR in October 2026 (2026-10-01 to 2026-10-31); INV-2026-0117; VAT 15% is 30.00 SAR.'
        self.assertEqual(identifier_spans(text), [])

    def test_oversized_or_non_text_input_is_refused(self):
        for bad in (None, 1, 'x' * 16385):
            with self.assertRaises(ValueError):
                identifier_spans(bad)


class Client(unittest.TestCase):
    def test_only_masked_text_leaves_and_categories_are_reported(self):
        seen = []
        result = echo_client(seen).redact(INVOICE)
        for value in VALUES:
            self.assertNotIn(value, seen[0])
            self.assertNotIn(value, result.text)
        self.assertEqual(set(result.categories), {'PHONE_NUMBER', 'IBAN_CODE', 'SAUDI_VAT_ID'})

    def test_with_the_email_layer_as_wired_in_the_front_door_and_financial_agent(self):
        seen = []
        result = DeterministicEmailRedactor(echo_client(seen)).redact(INVOICE)
        for value in VALUES + EMAILS:
            self.assertNotIn(value, seen[0])
        self.assertEqual(set(result.categories), {'EMAIL_ADDRESS', 'PHONE_NUMBER', 'IBAN_CODE', 'SAUDI_VAT_ID'})

    def test_a_masked_value_in_the_answer_fails_closed(self):
        client = echo_client([], reply={'text': 'call +966 55 014 2386', 'categories': []})
        with self.assertRaises(ControlFailure) as failure:
            client.redact(INVOICE)
        self.assertEqual((failure.exception.stage, failure.exception.category), ('presidio_anonymizer', 'unavailable'))

    def test_nothing_to_mask_is_sent_unchanged(self):
        seen = []
        self.assertEqual(echo_client(seen).redact('How much did I spend in October 2026?').categories, ())
        self.assertEqual(seen, ['How much did I spend in October 2026?'])


class OpsExplainer(unittest.TestCase):
    def test_finding_evidence_and_model_text_are_masked(self):
        from agent_platform.ops.explain import Explainer
        sent, seen = [], []
        reply = json.dumps({'en': 'The note mentions +966 53 207 9418.'})

        def gateway(request, timeout):
            sent.append(json.loads(request.data))
            return Response({'choices': [{'finish_reason': 'stop', 'message': {'content': reply}}]})
        finding = {'deployment': 'demo', 'namespace': 'apps', 'finding': 'CRASH_LOOP',
                   'evidence': {'last_message': INVOICE}, 'suggested_actions': []}
        result = Explainer('http://gateway.invalid:4000', 'k', echo_client(seen), opener=gateway)(finding)
        for value in VALUES:
            self.assertNotIn(value, json.dumps(sent))
            self.assertNotIn(value, json.dumps(seen))
        self.assertNotIn('+966 53 207 9418', result['untrusted_text'])


if __name__ == '__main__':
    unittest.main()
