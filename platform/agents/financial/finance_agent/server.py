"""The Financial Agent's own small web app (namespace agent-financial; reached by port-forward on 127.0.0.1:8081).

GET  /                  the page (static, CSP: self only)
POST /api/login         {"username","password"} -> signed session cookie (HttpOnly, SameSite=Strict) + CSRF token
POST /api/logout
GET  /api/me            who is signed in, session expiry, limits
GET  /api/expenses?month=YYYY-MM          the signed-in user's own expenses
POST /api/expenses      {"spent_on","merchant","category","amount","note"?}
POST /api/ask           {"question","language"} -> answer, how we know, privacy check, limits
GET  /healthz

Every state-changing request needs the exact Origin and the session's CSRF token. The Host header must be one of the
configured local addresses. The user id always comes from the verified session, never from the request.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import threading
from urllib.parse import parse_qs, urlsplit

from agent_platform import audit, release_version
from agent_platform.masking_scope import scope as masking_scope

UI = Path(__file__).resolve().parent / 'ui'
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/core.js': ('core.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
FONTS = {p.name for p in (UI / 'typeface').glob('*.woff2')}  # the design's own fonts, same origin, fixed names
HEADERS = {
    'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; img-src 'none'; "
                               "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store',
    'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Resource-Policy': 'same-origin',
}
COOKIE = 'fa_session'


class Handler(BaseHTTPRequestHandler):
    server_version = 'financial-agent'
    sys_version = ''

    def log_message(self, *_):
        pass

    def send(self, status, body, kind='application/json', cookie=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        for name, value in HEADERS.items():
            self.send_header(name, value)
        commit = release_version.source_commit()
        if commit:
            self.send_header('X-Platform-Source-Commit', commit)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        if cookie is not None:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(data)

    def host_ok(self):
        return self.headers.get_all('Host', []) == [self.headers.get('Host')] and self.headers.get('Host') in self.server.hosts

    def session(self):
        for part in (self.headers.get('Cookie') or '').split(';'):
            name, _, value = part.strip().partition('=')
            if name == COOKIE:
                return self.server.sessions.verify(value)
        return None

    def body(self):
        length = self.headers.get('Content-Length', '')
        if self.headers.get('Content-Type') != 'application/json' or not length.isdigit() or not 0 < int(length) <= 4096:
            return None
        try:
            value = json.loads(self.rfile.read(int(length)))
        except ValueError:
            return None
        return value if type(value) is dict else None

    def identity(self, user):
        return {'name':user['n'],'csrf':user['c'],'expires_at':user['exp'],
                'limits':self.server.agent.limits.remaining(user['u']),'masking_scope':masking_scope()}

    def do_GET(self):
        path = urlsplit(self.path)
        if path.path == '/healthz':
            return self.send(200, {'status': 'ok'})
        if not self.host_ok():
            return self.send(403, {'error': 'host_rejected'})
        if path.path in ASSETS:
            name, kind = ASSETS[path.path]
            return self.send(200, (UI / name).read_bytes(), kind)
        if path.path.startswith('/typeface/') and path.path[10:] in FONTS:
            return self.send(200, (UI / 'typeface' / path.path[10:]).read_bytes(), 'font/woff2')
        user = self.session()
        if user is None:
            return self.send(401, {'error': 'sign_in_required'})
        if path.path == '/api/me':
            return self.send(200, self.identity(user))
        if path.path == '/api/expenses':
            month = (parse_qs(path.query).get('month') or [''])[0]
            try:
                return self.send(200, {'month': month, 'expenses': self.server.store.list_expenses(user['u'], month)})
            except ValueError as error:
                return self.send(400, {'error': str(error)})
        return self.send(404, {'error': 'not_found'})

    def do_POST(self):
        path = urlsplit(self.path).path
        if not self.host_ok() or self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
            return self.send(403, {'error': 'origin_rejected'})
        body = self.body()
        if body is None:
            return self.send(400, {'error': 'json_body_required'})
        if path == '/api/login':
            return self.login(body)
        user = self.session()
        if user is None:
            return self.send(401, {'error': 'sign_in_required'})
        if self.headers.get('X-CSRF') != user['c']:
            return self.send(403, {'error': 'csrf_rejected'})
        if path == '/api/logout':
            self.server.sessions.revoke(user)
            self.server.agent.forget(user['u'])
            return self.send(200, {'signed_out': True}, cookie=COOKIE + '=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
        if path == '/api/expenses':
            try:
                new_id = self.server.store.add_expense(user['u'], body)
            except ValueError as error:
                return self.send(400, {'error': str(error)})
            audit.emit('finance_expense_added', 'agent-financial', user_ref=self.server.agent._user_ref(user['u']))
            return self.send(201, {'id': new_id})
        if path == '/api/ask':
            if set(body) != {'question', 'language'}:
                return self.send(400, {'error': 'fields: question, language'})
            return self.send(200, self.server.agent.ask(user['u'], body['question'], body['language']))
        return self.send(404, {'error': 'not_found'})

    def login(self, body):
        from finance_agent.auth import verify_password
        username, password = body.get('username'), body.get('password')
        client = self.client_address[0]  # the TCP peer; X-Forwarded-For is never trusted
        if (type(username) is not str or type(password) is not str or not 0 < len(username) <= 64
                or not 0 < len(password) <= 128):
            return self.send(400, {'error': 'username_and_password_required'})
        if self.server.throttle.blocked(username, client):
            audit.emit('finance_login_throttled', 'agent-financial')
            return self.send(429, {'error': 'too_many_attempts'})
        account = self.server.store.user(username)
        if not verify_password(account and account['password_hash'], password):
            self.server.throttle.failed(username, client)
            audit.emit('finance_login_failed', 'agent-financial')
            return self.send(401, {'error': 'wrong_username_or_password'})
        cookie, payload = self.server.sessions.issue(account['id'], account['display_name'])
        audit.emit('finance_login', 'agent-financial', user_ref=self.server.agent._user_ref(account['id']))
        return self.send(200, self.identity(payload),
                         cookie=COOKIE + '=' + cookie + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600')


def build(config, *, store=None, redactor=None, gateway=None):
    from finance_agent.agent import FinanceAgent, Gateway
    from finance_agent.auth import LoginThrottle, Sessions
    from finance_agent.store import Store
    if redactor is None:
        from agent_platform.redaction import RedactorClient, WindowedBoundaryBudget
        from runtime.phase3.deterministic_email import DeterministicEmailRedactor
        redactor = DeterministicEmailRedactor(RedactorClient('http://redactor.platform.svc.cluster.local:4003',
                                                             config['redactor_key'], budget=WindowedBoundaryBudget()))
    store = store or Store(config['web_db_url'], config['agent_db_url'])
    key = bytes.fromhex(config['session_key'])
    agent = FinanceAgent(store, redactor, gateway or Gateway(config['gateway_key']), audit_key=key)
    return store, Sessions(key), LoginThrottle(), agent


DRAIN_SECONDS = 10  # in-flight requests may finish within this, well inside the Pod's 30 s grace period


class Server(ThreadingHTTPServer):
    """ThreadingHTTPServer that counts in-flight requests, so a shutdown can wait for them (bounded)."""
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active, self._idle = 0, threading.Condition()

    def process_request_thread(self, request, client_address):
        with self._idle:
            self.active += 1
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._idle:
                self.active -= 1
                self._idle.notify_all()

    def drain(self, seconds):
        """Wait until no request is in flight, at most `seconds`. True if none was left."""
        with self._idle:
            return self._idle.wait_for(lambda: self.active == 0, seconds)


def serve(server, *, drain_seconds=DRAIN_SECONDS):
    """Serve until SIGTERM, then stop accepting, let in-flight requests finish (bounded) and return.

    The agent runs as PID 1, which ignores SIGTERM unless it installs a handler: without this, every rollout or
    scale-down waited the full grace period for SIGKILL. shutdown() blocks until serve_forever() returns, so it runs on
    its own thread, never inside the handler on the serving thread."""
    signal.signal(signal.SIGTERM, lambda signum, frame: threading.Thread(target=server.shutdown, daemon=True).start())
    server.serve_forever()
    server.server_close()  # stop accepting before draining
    return server.drain(drain_seconds)


def main():
    config = json.loads(Path('/secrets/agent/agent.json').read_text())
    required = {'gateway_key', 'redactor_key', 'web_db_url', 'agent_db_url', 'session_key'}
    if set(config) != required or not re.fullmatch(r'[0-9a-f]{64}', config['session_key']):
        raise SystemExit('financial:config')
    port = int(os.environ.get('AGENT_PORT', '8081'))
    server = Server(('0.0.0.0', port), Handler)
    server.hosts = {'127.0.0.1:%d' % port}
    server.store, server.sessions, server.throttle, server.agent = build(config)
    audit.emit('agent_started', 'agent-financial')
    drained = serve(server)
    audit.emit('agent_stopped', 'agent-financial', drained=drained)


if __name__ == '__main__':
    main()
