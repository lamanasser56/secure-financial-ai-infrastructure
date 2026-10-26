"""Current trusted frontdoor contract over real HTTP; only database and worker transport are synthetic."""
import http.client
from contextlib import closing
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'platform/agents/financial'))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from agent_platform.data_capability import CapabilityIssuer
from agent_platform import ui_assets
from agent_platform.financial_schema import metadata
from agent_platform.masking_scope import scope
from finance_agent.auth import Sessions, LoginThrottle, hash_password
from finance_agent.frontdoor import Forwarder
from finance_agent.server import Handler, Server

USER = '00000000-0000-4000-8000-000000000001'


class FinancialContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = Ed25519PrivateKey.generate()
        issuer = CapabilityIssuer(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                    serialization.NoEncryption()).decode(),
                                  key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())
        cls.password = hash_password('offline-test-only')
        cls.calls = []

        def dispatch(url, credential, body, **kwargs):
            issuer.verify(body['capability'], 'financial-demo')
            cls.calls.append((url, body.get('language')))
            return ({'status': 'forgotten'} if url.endswith('/forget') else {'status': 'answered', 'answer': 'إجابة اختبار'}), {}

        cls.server = Server(('127.0.0.1', 0), Handler)
        cls.server.hosts = {'127.0.0.1:%d' % cls.server.server_port}
        cls.server.sessions, cls.server.throttle = Sessions(b'a' * 32), LoginThrottle()
        cls.server.store = SimpleNamespace(user=lambda name: {'id': USER, 'display_name': 'اختبار', 'password_hash': cls.password} if name == 'demo' else None)
        cls.server.agent = Forwarder(issuer, {USER: {'agent': 'financial-demo', 'url': 'http://offline-worker/ask', 'key': 'offline-key'}}, dispatch=dispatch)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(5)

    def request(self, method, path, body=None, cookie=None, csrf=None):
        host = next(iter(self.server.hosts))
        headers = {'Host': host, 'Origin': 'http://' + host, 'Content-Type': 'application/json'}
        if cookie:
            headers['Cookie'] = cookie
        if csrf:
            headers['X-CSRF'] = csrf
        with closing(http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)) as conn:
            conn.request(method, path, None if body is None else json.dumps(body), headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read()), response.getheader('Set-Cookie')

    def test_real_session_metadata_arabic_dispatch_and_revocation(self):
        self.assertEqual(self.request('GET', '/api/me')[0], 401)
        code, login, cookie = self.request('POST', '/api/login', {'username': 'demo', 'password': 'offline-test-only'})
        self.assertEqual(code, 200)
        cookie = cookie.split(';')[0]
        self.assertEqual(login['schema'], metadata())
        self.assertEqual(login['masking_scope_ar'], scope('ar'))
        self.assertEqual({row['code'] for row in login['masking_scope_ar']['supported']}, {row['code'] for row in scope()['supported']})
        self.assertEqual(login['masking_scope_ar']['not_masked'], ['أسماء الأشخاص', 'أرقام جوازات السفر'])
        self.assertEqual(self.request('GET', '/api/me', cookie=cookie)[1]['schema'], login['schema'])
        self.assertEqual(self.request('POST', '/api/ask', {'question': 'كم أنفقت؟', 'language': 'ar'}, cookie, login['csrf'])[1]['answer'], 'إجابة اختبار')
        self.assertEqual(self.calls[-1], ('http://offline-worker/ask', 'ar'))
        self.assertEqual(self.request('POST', '/api/logout', {}, cookie, 'wrong')[0], 403)
        self.assertEqual(self.request('GET', '/api/me', cookie=cookie)[0], 200)
        self.assertTrue(self.request('POST', '/api/logout', {}, cookie, login['csrf'])[1]['signed_out'])
        self.assertEqual(self.calls[-1][0], 'http://offline-worker/forget')
        self.assertEqual(self.request('GET', '/api/me', cookie=cookie)[0], 401)

    def test_frontdoor_limit_is_not_misreported_as_worker_unavailability(self):
        previous = self.server.agent
        agent = Forwarder(previous.issuer, previous.routes, dispatch=previous.dispatch)
        for _ in range(20):
            self.assertEqual(agent.ask(USER, 'اختبار حدود محلي', 'ar')['status'], 'answered')
        self.assertEqual(agent.ask(USER, 'هذا الطلب مرفوض قبل العامل', 'ar')['reason'], 'rate_limited')
        self.assertEqual(agent.limits.remaining(USER)['questions_this_hour'], 0)

    def test_masking_translation_refuses_unknown_language(self):
        with self.assertRaises(ValueError):
            scope('unknown')

    def test_every_shared_route_returns_the_canonical_bytes_and_security_headers(self):
        host = next(iter(self.server.hosts))
        for route, kind in ui_assets.inventory().items():
            with self.subTest(route=route), closing(http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)) as conn:
                conn.request('GET', route, headers={'Host': host})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader('Content-Type'), kind)
                self.assertEqual(response.read(), ui_assets.read(route)[0])
                self.assertIn("font-src 'self'", response.getheader('Content-Security-Policy'))
                self.assertNotIn('unsafe-inline', response.getheader('Content-Security-Policy'))
