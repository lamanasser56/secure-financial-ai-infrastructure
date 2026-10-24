"""Independent assessment regressions. Synthetic models and stores; no live boundary claims."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from finance_agent import agent as module
from finance_agent.auth import Sessions
from test_finance_agent import LAMA, Model, Redactor, Store, run


class FinancialSecurityRC1(unittest.TestCase):
    def answer(self, text, *, note='', merchant='Cafe', tool='monthly_total', amount=2450):
        store = Store({LAMA: [(1, '2026-10-02', merchant, 'food', amount, note)]})
        steps = ([{'action': 'tool', 'tool': tool, 'args': {'month': '2026-10'}}] if tool else [])
        return run(Model(*steps, {'action': 'answer', 'text': text}), store=store)[1]

    def test_embedded_digits_do_not_bypass_grounding(self):
        for amount in ('SAR9999', 'SAR٩٩٩٩', 'USD9999', 'ر.س٩٩٩٩', 'x9999', '９９９９ SAR', '9\u200b999 SAR'):
            with self.subTest(amount=amount):
                self.assertEqual(self.answer('Total expenses: ' + amount, tool=None).get('reason'), 'ungrounded_numbers')

    def test_money_requires_sar_values_in_major_units(self):
        for amount in ('2450 SAR', '2026 SAR', '10 SAR', '1 SAR', '-24.50 SAR', '−24.50 SAR', 'USD24.50', '24.50 USD'):
            with self.subTest(amount=amount):
                self.assertEqual(self.answer('You spent ' + amount).get('reason'), 'ungrounded_numbers')

    def test_numeric_notation_cannot_round_or_split_into_grounded_values(self):
        for text, amount in (('You spent 24.5001 SAR.', 2450), ('You spent 24.5000000000000000001 SAR.', 2450),
                             ('You spent 1e10 SAR.', 1000),
                             ('You spent 1e1 SAR.', 100), ('Your spending rose 1%.', 2450)):
            with self.subTest(text=text):
                self.assertEqual(self.answer(text, amount=amount).get('reason'), 'ungrounded_numbers')

    def test_valid_money_and_structural_dates_remain_usable(self):
        for amount in ('24.50 SAR', 'SAR24.50', '٢٤٫٥٠ ر.س', '24,50 SAR'):
            with self.subTest(amount=amount):
                self.assertEqual(self.answer('In October 2026 you spent ' + amount + ' on 1 expense.')['status'], 'answered')

    def test_unquoted_notes_do_not_ground_business_claims(self):
        for note in ('invoice was approved', 'Your invoice was approved'):
            with self.subTest(note=note):
                self.assertEqual(self.answer('Your invoice was approved.', note=note, tool='find_transactions').get('reason'),
                                 'ungrounded_claim')

    def test_exact_quoted_note_is_data(self):
        for left, right in (('"', '"'), ('“', '”'), ('«', '»')):
            with self.subTest(quote=left):
                self.assertEqual(self.answer('Your note says ' + left + 'invoice was approved' + right + '.',
                                             note='invoice was approved', tool='find_transactions')['status'], 'answered')

    def test_quote_cannot_whitelist_another_claim(self):
        self.assertEqual(self.answer('Your note says "invoice was approved". Your invoice was approved.',
                                     note='invoice was approved', tool='find_transactions').get('reason'), 'ungrounded_claim')

    def test_malformed_tool_names_are_bounded_and_audited(self):
        for name in ([], {}, None, 4):
            with self.subTest(name=name):
                with patch('agent_platform.audit.emit') as emit:
                    _, result = run(Model({'action': 'tool', 'tool': name, 'args': {}}))
                self.assertEqual(result.get('reason'), 'tool_not_allowed')
                emit.assert_called_once()
                self.assertEqual(emit.call_args.kwargs['request_id'], result['request_id'])

    def test_malformed_provider_envelopes_are_bounded_and_audited(self):
        class Response:
            headers = {}
            def __init__(self, value): self.value = value
            def read(self, size): return json.dumps(self.value).encode()
            def __enter__(self): return self
            def __exit__(self, *args): pass
        for value in ([], None, {}, {'choices': [None]}, {'choices': [{'message': 'invalid', 'finish_reason': 'stop'}]},
                      {'choices': {'bad': True}}, {'choices': [{'message': {'content': 'x'}, 'finish_reason': 'length'}]}):
            with self.subTest(value=value), patch('agent_platform.audit.emit') as emit:
                gateway = module.Gateway('synthetic', opener=lambda *a, **k: Response(value))
                _, result = run(gateway)
                self.assertEqual(result['status'], 'blocked')
                self.assertEqual(result['trace']['model_calls'], 1)
                self.assertGreater(result['trace']['tokens'], 0)
                emit.assert_called_once()

    def test_unexpected_gateway_failure_has_one_sanitized_turn_record(self):
        class Broken:
            def complete(self, messages): raise RuntimeError('DO NOT LOG THIS SYNTHETIC CONTENT')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            _, result = run(Broken())
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertNotIn('DO NOT LOG', out.getvalue())
        self.assertGreater(result['trace']['tokens'], 0)

    def test_malformed_tool_result_is_not_a_success_or_missing_audit(self):
        with patch.dict(module.TOOLS, {'monthly_total': (lambda *a: {'wrong': object()}, 'synthetic')}):
            with patch('agent_platform.audit.emit') as emit:
                _, result = run(Model({'action': 'tool', 'tool': 'monthly_total', 'args': {'month': '2026-10'}}))
        self.assertEqual(result['status'], 'blocked')
        emit.assert_called_once()

    def test_session_malformed_non_ascii_input_is_rejected(self):
        sessions = Sessions(b's' * 32)
        cookie, _ = sessions.issue(LAMA, 'Synthetic')
        for value in (cookie.split('.')[0] + '.é', 'é.' + cookie.split('.')[1], None, [], b'bytes', 'x.' * 3000):
            with self.subTest(kind=type(value).__name__):
                self.assertIsNone(sessions.verify(value))
        self.assertEqual(sessions.verify(cookie)['u'], LAMA)
