"""The app's conversation entry point: one request ID per turn, bound for the redactor/gateway and returned."""
import contextlib
import io
import json
import unittest

from agent_platform import app, request_context


class Inner:
    def __init__(self):
        self.seen = []

    def turn(self, token, request):
        self.seen.append(request_context.current())
        return {'answer': 'ok'}

    def reset(self, token, request):
        return {'reset': True}


class RequestIdEntryPoint(unittest.TestCase):
    def test_turn_binds_one_id_and_returns_it(self):
        inner = Inner()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = app.RequestIdConversations(inner).turn('t', {})
        self.assertEqual(result['answer'], 'ok')
        self.assertRegex(result['request_id'], r'^[0-9a-f]{32}$')
        self.assertEqual(inner.seen, [result['request_id']])  # the core ran inside the bound request
        self.assertIsNone(request_context.current())  # not left bound afterwards
        self.assertEqual(json.loads(out.getvalue())['request_id'], result['request_id'])

    def test_each_turn_gets_its_own_id_and_other_calls_are_delegated(self):
        wrapper = app.RequestIdConversations(Inner())
        with contextlib.redirect_stdout(io.StringIO()):
            ids = {wrapper.turn('t', {})['request_id'] for _ in range(5)}
        self.assertEqual(len(ids), 5)
        self.assertEqual(wrapper.reset('t', {}), {'reset': True})

    def test_gateway_transport_carries_the_id_when_bound(self):
        sent = []
        send = app.instructed(lambda url, payload, timeout, headers: sent.append((payload, headers)) or {})
        base = {'messages': [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}]}
        rid = request_context.new()
        with request_context.bind(rid):
            send('http://g', base, 8, {'Authorization': 'Bearer x'})
        send('http://g', base, 8, {'Authorization': 'Bearer x'})
        (payload, headers), (plain_payload, plain_headers) = sent
        self.assertEqual((headers['X-Request-ID'], payload['metadata']), (rid, {'request_id': rid}))
        self.assertNotIn('X-Request-ID', plain_headers)
        self.assertNotIn('metadata', plain_payload)

    def test_agent_core_audit_lines_carry_the_request_id(self):
        out = io.StringIO()
        rid = request_context.new()
        with contextlib.redirect_stdout(out), request_context.bind(rid):
            app.AuditSink('turn').append({'event_id': 'e', 'outcome': 'ok', 'prompt': 'must be dropped'})
        line = json.loads(out.getvalue())
        self.assertEqual((line['request_id'], line['audit_event']), (rid, 'agent_turn'))
        self.assertNotIn('prompt', line)


class RedactorHeader(unittest.TestCase):
    def test_redactor_reads_only_a_well_formed_request_id(self):
        import types
        from agent_platform.programs.redactor_server import Handler
        handler = object.__new__(Handler)
        good = request_context.new()
        for value, expected in ((good, good), ('', None), ('not-an-id', None), (good + '0', None), (good.upper(), None)):
            handler.headers = types.SimpleNamespace(get=lambda name, default='', v=value: v if name == 'X-Request-ID' else default)
            self.assertEqual(handler.request_id(), expected)


if __name__ == '__main__':
    unittest.main()
