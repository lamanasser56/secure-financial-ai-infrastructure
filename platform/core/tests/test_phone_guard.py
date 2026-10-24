"""Phone pre-mask coverage and its fail-closed SDP integration, entirely offline."""
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from agent_platform.programs.phone_guard import mask_phones
from agent_platform.programs.redactor_server import Capacity, Handler


class PhoneGuard(unittest.TestCase):
    def test_inline_us_and_saudi_formats_in_prose_and_json(self):
        for phone in ('415-555-2671', '+1 (415) 555-2671', '0501234567',
                      '+966 50 123 4567', '050-123-4567', '٠٥٠ ١٢٣ ٤٥٦٧',
                      '+٩٦٦ ٥٠ ١٢٣ ٤٥٦٧', '۰۵۰۱۲۳۴۵۶۷'):
            for text in ('Contact: ' + phone + ' today.', json.dumps({'phone': phone}, ensure_ascii=False)):
                with self.subTest(text=text):
                    masked, found = mask_phones(text)
                    self.assertTrue(found)
                    self.assertNotIn(phone, masked)
                    self.assertIn('PHONE_NUMBER', masked)

    def test_non_phone_values_and_embedded_identifiers_are_preserved(self):
        for text in ('Total 24.50 SAR on 2026-10-24', 'refA0501234567Z', '005012345678'):
            self.assertEqual(mask_phones(text), (text, False))

    def invoke(self, text, provider):
        raw = json.dumps({'text': text}).encode()
        response = Mock()
        handler = SimpleNamespace(
            path='/redact', headers={'Content-Length': str(len(raw)), 'Content-Type': 'application/json'},
            rfile=io.BytesIO(raw), client=lambda: 'app', request_id=lambda: 'synthetic', reply=response,
            server=SimpleNamespace(budget=SimpleNamespace(current=lambda: provider), capacity=Capacity(('app',))))
        with patch('agent_platform.programs.redactor_server.audit'):
            Handler.do_POST(handler)
        return response.call_args.args

    def test_premask_still_invokes_sdp_and_merges_its_categories(self):
        provider = Mock()
        provider.redact.return_value = SimpleNamespace(text='PHONE_NUMBER EMAIL_ADDRESS', categories=('EMAIL_ADDRESS',))
        status, body = self.invoke('415-555-2671 alice@example.invalid', provider)
        provider.redact.assert_called_once_with('PHONE_NUMBER alice@example.invalid')
        self.assertEqual(status, 200)
        self.assertEqual(body['categories'], ['EMAIL_ADDRESS', 'PHONE_NUMBER'])

    def test_sdp_failure_never_returns_locally_masked_content(self):
        provider = Mock()
        provider.redact.side_effect = TimeoutError('synthetic outage')
        self.assertEqual(self.invoke('415-555-2671', provider), (503, {'code': 'REDACTION_UNAVAILABLE'}))
        provider.redact.assert_called_once_with('PHONE_NUMBER')

    def test_non_phone_input_still_invokes_sdp(self):
        provider = Mock()
        provider.redact.return_value = SimpleNamespace(text='safe', categories=())
        self.assertEqual(self.invoke('safe', provider), (200, {'text': 'safe', 'categories': []}))
        provider.redact.assert_called_once_with('safe')
