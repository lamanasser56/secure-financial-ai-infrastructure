"""Loopback-only, single-thread private demo UI with fixed startup identities.

This is simulated authentication, not a production user-authentication service.
Free text is bounded and governed. No cloud credentials, upload or live switch.
"""

import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
from runtime.agents.conversations import ConversationRejected, ConversationStore
from runtime.agents.demo import make_demo
from runtime.agents.schemas import ROOT, read_fixed

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/i18n.json": ("i18n.json", "application/json; charset=utf-8"),
    "/operations.html": ("operations.html", "text/html; charset=utf-8"),
    "/operations.js": ("operations.js", "text/javascript; charset=utf-8"),
}


class DemoServer(HTTPServer):
    allow_reuse_address = False

    def __init__(self, address=("127.0.0.1", 8765), *, user="demo-alpha", agents=None,
                 composition=None, operations=None):
        if (
            address[0] != "127.0.0.1"
            or type(address[1]) is not int
            or not 0 <= address[1] <= 65535
        ):
            raise ValueError("ui:loopback_only")
        self.agents = agents if agents is not None else {
            p: make_demo(p, user) for p in ("infrastructure", "financial")}
        self.composition = composition
        self.operations = operations
        self.conversations = ConversationStore(self.agents)
        super().__init__(address, Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.cookie_name = f"demo_session_{self.server_port}"

    def server_close(self):
        self.conversations.sessions.clear()
        super().server_close()

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(2)
        return connection, address

    def handle_error(self, request, client_address):
        # Disconnected/malformed local clients must not emit request details.
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "PrivateDemo"
    sys_version = ""

    def log_message(self, *args):
        # No request bodies, headers, credentials or filesystem paths in logs.
        pass

    def respond(
        self,
        status,
        value,
        content_type="application/json; charset=utf-8",
        *,
        cookie=None,
    ):
        body = (
            value
            if isinstance(value, bytes)
            else json.dumps(value, ensure_ascii=False).encode()
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        self.send_header("Connection", "close")
        if cookie is not None:
            self.send_header(
                "Set-Cookie",
                f"{self.server.cookie_name}={cookie}; HttpOnly; SameSite=Strict; Path=/api",
            )
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def boundary(self, post=False):
        hosts = self.headers.get_all("Host", [])
        origins = self.headers.get_all("Origin", [])
        if (
            hosts != [self.server.origin.removeprefix("http://")]
            or len(origins) > 1
            or (origins and origins[0] != self.server.origin)
            or (post and origins != [self.server.origin])
        ):
            self.respond(403, {"error": "private_boundary_rejected"})
            return False
        if any(
            self.headers.get_all(key, [])
            for key in (
                "Authorization",
                "X-Tenant-ID",
                "X-Forwarded-For",
                "X-Forwarded-Host",
                "X-Forwarded-Proto",
            )
        ):
            self.respond(403, {"error": "request_identity_override_rejected"})
            return False
        return True

    def do_GET(self):
        if not self.boundary():
            return
        if self.path == "/api/bootstrap":
            try:
                token, session = self.server.conversations.bootstrap(
                    self.session_token()
                )
            except ConversationRejected:
                self.respond(503, {"error": "session_capacity"})
                return
            self.respond(
                200,
                {
                    "csrf": session.csrf,
                    "mode": 'gateway' if self.server.composition=='supervised_candidate_live' else "offline_simulation",
                    "authentication": 'fixture_issuer_scope_accepted' if self.server.composition=='supervised_candidate_live' else "simulated",
                    "synthetic_only": True,
                    **({'operations_available': True} if self.server.operations else {}),
                    **({"composition": self.server.composition} if self.server.composition is not None else {}),
                },
                cookie=token,
            )
        elif self.path in ASSETS:
            name, kind = ASSETS[self.path]
            try:
                self.respond(
                    200,
                    read_fixed(
                        (
                            ROOT / "demo/i18n.json"
                            if name == "i18n.json"
                            else ROOT / "demo/ui" / name
                        ),
                        32768,
                    ).encode(),
                    kind,
                )
            except Exception:
                self.respond(500, {"error": "asset_unavailable"})
        else:
            self.respond(404, {"error": "not_found"})

    def session_token(self):
        cookies = self.headers.get_all("Cookie", [])
        if len(cookies) != 1 or len(cookies[0]) > 512:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(cookies[0])
            value = cookie[self.server.cookie_name].value
            return value if re.fullmatch(r"[A-Za-z0-9_-]{43}", value) else None
        except Exception:
            return None

    def do_POST(self):
        if not self.boundary(post=True):
            return
        if self.path not in {"/api/conversation", "/api/reset", "/api/operations"}:
            self.respond(404, {"error": "not_found"})
            return
        token = self.session_token()
        try:
            session = self.server.conversations.session(token)
        except ConversationRejected:
            self.respond(403, {"error": "session_required"})
            return
        tokens = self.headers.get_all("X-Demo-CSRF", [])
        if (
            len(tokens) != 1
            or not tokens[0].isascii()
            or not hmac.compare_digest(tokens[0], session.csrf)
        ):
            self.respond(403, {"error": "csrf_rejected"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        if (
            self.headers.get_all("Transfer-Encoding", [])
            or len(lengths) != 1
            or not 1 <= len(lengths[0]) <= 4
            or not lengths[0].isascii()
            or not lengths[0].isdigit()
            or not 1 <= int(lengths[0]) <= 4096
        ):
            self.respond(413, {"error": "bounded_body_required"})
            return
        if self.headers.get_all("Content-Type", []) != ["application/json"]:
            self.respond(415, {"error": "json_required"})
            return
        try:
            body = self.rfile.read(int(lengths[0]))
            if len(body) != int(lengths[0]):
                raise ValueError
            if self.path == '/api/operations':
                from runtime.agents.operations_service import decode_request
                request = decode_request(body)
            else:
                request = json.loads(body)
            if self.path == '/api/operations':
                if self.server.operations is None:
                    self.respond(503, {'error': 'operations_unavailable'})
                    return
                from runtime.agents.operations import OperationsBlocked
                try:
                    result = self.server.operations.handle(request)
                except OperationsBlocked as failure:
                    self.respond(403, {'error': failure.code,
                        'budgets': self.server.operations.controller.budgets()})
                    return
            else:
                result = (
                self.server.conversations.turn(token, request)
                if self.path == "/api/conversation"
                else self.server.conversations.reset(token, request)
                )
        except ConversationRejected as failure:
            self.respond(403, {"error": str(failure)})
            return
        except Exception:
            self.respond(400, {"error": "invalid_request"})
            return
        self.respond(200, result)

    def do_OPTIONS(self):
        self.respond(405, {"error": "method_not_allowed"})
