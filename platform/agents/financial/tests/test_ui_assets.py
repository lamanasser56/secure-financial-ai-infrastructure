"""The Financial Agent serves its UI (same design as the console): fixed files, own fonts, a CSP that allows nothing else,
and the real sign-in still guards every data route. No database: the stub store from ui_stub.py stands in."""
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finance_agent import server  # noqa: E402
from test_finance_agent import Redactor  # noqa: E402
from ui_stub import Cycling, StubStore  # noqa: E402


class UiAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        httpd.daemon_threads = True
        cls.port = httpd.server_address[1]
        httpd.hosts = {'127.0.0.1:%d' % cls.port}
        httpd.store, httpd.sessions, httpd.throttle, httpd.agent = server.build({'session_key': 'ab' * 32}, store=StubStore(),
                                                                                redactor=Redactor(), gateway=Cycling())
        cls.httpd = httpd
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path, host=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request('GET', path, headers={'Host': host or '127.0.0.1:%d' % self.port})
        response = conn.getresponse()
        return response.status, response.read(), response

    def test_files_and_fonts_are_served_without_a_session(self):
        for path, kind in (('/', 'text/html'), ('/app.js', 'text/javascript'), ('/core.js', 'text/javascript'), ('/style.css', 'text/css'),
                           ('/fonts/ibm-plex-sans-latin-400-normal.woff2', 'font/woff2')):
            status, body, response = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(response.getheader('Content-Type').startswith(kind), path)
            csp = response.getheader('Content-Security-Policy')
            self.assertIn("font-src 'self'", csp)
            self.assertIn("default-src 'none'", csp)
            self.assertNotRegex(csp, r'unsafe-inline|https?:')

    def test_only_the_listed_fonts_by_exact_name(self):
        for path in ('/fonts/nope.woff2', '/fonts/', '/fonts/../app.js', '/fonts/LICENSE-barlow.txt', '/fonts/%2e%2e/app.js', '/other.js'):
            status = self.get(path)[0]
            self.assertIn(status, (401, 404), path)  # never a file: anything else needs a session first
            self.assertNotEqual(status, 200, path)

    def test_data_routes_still_need_the_real_sign_in(self):
        for path in ('/api/me', '/api/expenses?month=2026-10'):
            self.assertEqual(self.get(path)[0], 401)
        self.assertEqual(self.get('/', host='evil.example')[0], 403)

    def test_sign_in_and_trace_reach_the_ui_unchanged(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        host = '127.0.0.1:%d' % self.port
        conn.request('POST', '/api/login', body=json.dumps({'username': 'demo', 'password': 'demo-password-1'}),
                     headers={'Host': host, 'Origin': 'http://' + host, 'Content-Type': 'application/json'})
        response = conn.getresponse()
        login = json.loads(response.read())
        self.assertEqual(response.status, 200)
        cookie = response.getheader('Set-Cookie').split(';')[0]
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request('POST', '/api/ask', body=json.dumps({'question': 'How much did I spend in October 2026?', 'language': 'en'}),
                     headers={'Host': host, 'Origin': 'http://' + host, 'Content-Type': 'application/json', 'Cookie': cookie, 'X-CSRF': login['csrf']})
        answer = json.loads(conn.getresponse().read())
        self.assertEqual(answer['status'], 'answered')
        trace = answer['trace']
        for key in ('user_ref', 'redaction', 'data_access', 'grounding_result', 'cost_usd', 'model', 'request_id', 'tool_calls'):
            self.assertIn(key, trace)  # exactly what the UI renders as steps


if __name__ == '__main__':
    unittest.main()
