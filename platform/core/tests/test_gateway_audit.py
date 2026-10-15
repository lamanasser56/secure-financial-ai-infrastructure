"""The gateway hook's audit line: the caller's request ID, bounded fields, no content, never blocks the response."""
import contextlib
import io
import json
from pathlib import Path
import sys
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/agent_platform/programs'))
import gateway_hooks  # noqa: E402

RID = 'a1' * 16


def response(**overrides):
    base = dict(model='gemini-test', usage=types.SimpleNamespace(total_tokens=321), _hidden_params={'response_cost': 0.00123},
                choices=[])
    return types.SimpleNamespace(**dict(base, **overrides))


class GatewayAudit(unittest.TestCase):
    def test_request_id_from_metadata_or_header(self):
        key = types.SimpleNamespace(key_alias='agent-financial')
        for data in ({'metadata': {'request_id': RID}}, {'proxy_server_request': {'headers': {'x-request-id': RID}}}):
            with self.subTest(data=list(data)):
                fields = gateway_hooks.audit_fields(data, key, response())
                self.assertEqual(fields, {'request_id': RID, 'key_alias': 'agent-financial', 'model': 'gemini-test',
                                          'total_tokens': 321, 'cost_usd': 0.00123})

    def test_malformed_values_are_dropped_not_logged(self):
        key = types.SimpleNamespace(key_alias='sk-0123456789abcdef')  # looks like a key: never an alias
        fields = gateway_hooks.audit_fields({'metadata': {'request_id': 'x' * 40 + '\n{"inject":1}'}}, key,
                                            response(model='bad model\n', _hidden_params={'response_cost': 'free'}))
        self.assertEqual(fields, {'request_id': None, 'key_alias': None, 'model': None, 'total_tokens': 321, 'cost_usd': None})

    def test_audit_line_is_one_json_line_without_content(self):
        out = io.StringIO()
        reply = response(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='SECRET REPLY'))])
        with contextlib.redirect_stdout(out):
            gateway_hooks.emit_audit(gateway_hooks.audit_fields({'metadata': {'request_id': RID}, 'messages': ['SECRET PROMPT']},
                                                               types.SimpleNamespace(key_alias='ops-explain'), reply))
        line = json.loads(out.getvalue())
        self.assertEqual((line['audit_event'], line['component'], line['request_id']), ('gateway_request', 'gateway', RID))
        for secret in ('SECRET REPLY', 'SECRET PROMPT'):
            self.assertNotIn(secret, out.getvalue())
        self.assertEqual(len(out.getvalue().splitlines()), 1)

    def test_a_broken_response_object_yields_no_record_and_no_exception(self):
        fields = gateway_hooks.audit_fields(None, None, None)
        self.assertEqual(fields['request_id'], None)


if __name__ == '__main__':
    unittest.main()
