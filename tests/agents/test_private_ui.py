import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest
from unittest import mock
import urllib.error

from runtime.agents.demo import make_demo
from runtime.agents.web import DemoServer
from runtime.phase3.adapters import _post_json


class PrivateUITests(unittest.TestCase):
    def setUp(self):
        self.server = DemoServer(("127.0.0.1", 0))
        self.origin = self.server.origin
        self.cookie = None
        status, headers, body = self.call("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = json.loads(body)["csrf"]

    def tearDown(self):
        self.server.server_close()
        self.assertFalse(self.server.conversations.sessions)

    def call(self, method, path, body=None, headers=None):
        outcomes = []
        standard = {"Cookie": self.cookie} if self.cookie else {}
        standard.update(headers or {})

        def client():
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.server.server_port, timeout=5
            )
            try:
                connection.request(method, path, body=body, headers=standard)
                response = connection.getresponse()
                outcomes.append(
                    (response.status, dict(response.getheaders()), response.read())
                )
            finally:
                connection.close()

        thread = threading.Thread(target=client)
        thread.start()
        self.server.handle_request()
        thread.join(6)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(outcomes), 1)
        return outcomes[0]

    def payload(self, **extra):
        return {
            "agent": "financial",
            "language": "en",
            "question": "What are my total expenses for 2026-01?",
            "evidence_source": None,
            "conversation_id": None,
            **extra,
        }

    def post(self, payload=None, headers=None, path="/api/conversation"):
        standard = {
            "Origin": self.origin,
            "X-Demo-CSRF": self.csrf,
            "Content-Type": "application/json",
        }
        standard.update(headers or {})
        return self.call("POST", path, json.dumps(payload or self.payload()), standard)

    def test_private_assets_and_security_headers(self):
        status, headers, body = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn('dir="ltr"', body.decode())
        self.assertIn('lang="en"', body.decode())
        for identifier in (
            "language",
            "question",
            "send",
            "history",
            "new-conversation",
        ):
            self.assertIn(f'id="{identifier}"', body.decode())
        self.assertIn('role="tablist"', body.decode())
        self.assertIn('aria-live="polite"', body.decode())
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_bootstrap_credentials_are_private_and_session_cookie_is_httponly(self):
        status, headers, body = self.call("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        value = json.loads(body)
        self.assertEqual(
            set(value), {"csrf", "mode", "authentication", "synthetic_only"}
        )
        for flag in ("HttpOnly", "SameSite=Strict", "Path=/api"):
            self.assertIn(flag, headers["Set-Cookie"])
        self.assertEqual(value["authentication"], "simulated")
        for _, authorization in self.server.agents.values():
            self.assertFalse(
                authorization in body.decode(),
                "Startup credential unexpectedly present",
            )

    def test_ui_financial_and_infrastructure_complete_in_both_languages(self):
        for profile, question, lang in (
            ("financial", "What were my expenses in January 2026?", "en"),
            ("infrastructure", "لماذا فشل تصدير صورة Docker؟", "ar"),
        ):
            status, _, body = self.post(
                self.payload(agent=profile, question=question, language=lang)
            )
            self.assertEqual(status, 200)
            frame = json.loads(body)
            self.assertEqual(frame["response"]["status"], "completed")
            self.assertEqual(frame["response"]["mode"], "offline_simulation")
            self.assertEqual(frame["response"]["language"], lang)

    def test_missing_period_and_followup_keep_same_conversation(self):
        status, _, body = self.post(
            self.payload(question="Show my expense totals and categories.")
        )
        self.assertEqual(status, 200)
        first = json.loads(body)
        response = first["response"]
        self.assertEqual(response["status"], "clarification_required")
        self.assertEqual(
            (response["model_requests"], response["tool_executions"]), (0, 0)
        )
        self.assertNotIn("facts", response)
        status, _, body = self.post(
            self.payload(
                question="يناير ٢٠٢٦",
                language="ar",
                conversation_id=first["conversation_id"],
            )
        )
        second = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(second["conversation_id"], first["conversation_id"])
        self.assertEqual(second["turn_number"], 2)
        self.assertEqual(second["response"]["status"], "completed")
        self.assertEqual(
            second["response"]["presentation"]["financial"]["total"], "SAR 240.00"
        )

    def test_report_preserves_integers_and_omits_conversation_content(self):
        status, _, body = self.post()
        self.assertEqual(status, 200)
        frame = json.loads(body)
        report = frame["report"]
        finance = report["presentation"]["financial"]
        self.assertEqual(finance["total"], "SAR 240.00")
        self.assertEqual(
            [c["amount"] for c in finance["categories"]], ["SAR 200.00", "SAR 40.00"]
        )
        self.assertEqual(report["facts"][0]["result"]["total_minor_units"], 24000)
        usage = report["presentation"]["usage"]
        self.assertEqual(usage["simulated_model_requests"], 3)
        self.assertEqual(usage["external_provider_calls"], 0)
        self.assertIsNone(usage["token_usage"])
        self.assertIsNone(usage["cost"])
        for field in (
            "question",
            "answer",
            "history",
            "csrf",
            "conversation_id",
            "_retained_input",
            "_continuation",
        ):
            self.assertNotIn(field, report)
        self.assertNotIn(self.payload()["question"], json.dumps(report))

    def test_cross_session_conversation_access_is_denied(self):
        _, _, body = self.post()
        frame = json.loads(body)
        _, headers, body = self.call("GET", "/api/bootstrap", headers={"Cookie": ""})
        second_cookie = headers["Set-Cookie"].split(";", 1)[0]
        second_csrf = json.loads(body)["csrf"]
        status, _, _ = self.post(
            self.payload(conversation_id=frame["conversation_id"]),
            headers={"Cookie": second_cookie, "X-Demo-CSRF": second_csrf},
        )
        self.assertEqual(status, 403)
        status, _, _ = self.post(
            {"agent": "financial", "conversation_id": frame["conversation_id"]},
            headers={"Cookie": second_cookie, "X-Demo-CSRF": second_csrf},
            path="/api/reset",
        )
        self.assertEqual(status, 403)

    def test_trusted_tenant_change_cannot_continue_prior_conversation(self):
        _, _, body = self.post()
        identifier = json.loads(body)["conversation_id"]
        self.server.agents["financial"] = make_demo("financial", "demo-beta")
        self.assertEqual(self.post(self.payload(conversation_id=identifier))[0], 403)

    def test_explicit_reset_deletes_context_and_allows_new_conversation(self):
        _, _, body = self.post()
        identifier = json.loads(body)["conversation_id"]
        status, _, _ = self.post(
            {"agent": "financial", "conversation_id": identifier}, path="/api/reset"
        )
        self.assertEqual(status, 200)
        self.assertFalse(
            next(iter(self.server.conversations.sessions.values())).conversations
        )
        _, _, body = self.post()
        self.assertNotEqual(json.loads(body)["conversation_id"], identifier)

    def test_hostname_rebinding_and_cross_origin_are_rejected(self):
        for headers in (
            {"Host": "evil.invalid"},
            {"Origin": "https://evil.invalid"},
            {"Host": "localhost"},
        ):
            self.assertEqual(
                self.call("GET", "/api/bootstrap", headers=headers)[0], 403
            )
        self.assertEqual(self.post(headers={"Origin": "https://evil.invalid"})[0], 403)

    def test_missing_origin_session_and_wrong_csrf_are_rejected(self):
        self.assertEqual(
            self.call(
                "POST",
                "/api/conversation",
                body="{}",
                headers={"Content-Type": "application/json", "X-Demo-CSRF": self.csrf},
            )[0],
            403,
        )
        self.assertEqual(self.post(headers={"X-Demo-CSRF": "wrong"})[0], 403)
        self.assertEqual(self.post(headers={"Cookie": ""})[0], 403)

    def test_request_headers_and_payload_cannot_override_context_or_configuration(self):
        for header in (
            "Authorization",
            "X-Tenant-ID",
            "X-Forwarded-For",
            "X-Forwarded-Host",
            "X-Forwarded-Proto",
        ):
            self.assertEqual(self.post(headers={header: "untrusted"})[0], 403)
        for key in (
            "tenant_id",
            "identity",
            "gateway_url",
            "model",
            "credential",
            "history",
            "context",
            "limits",
            "period",
        ):
            self.assertEqual(self.post(self.payload(**{key: "untrusted"}))[0], 400)

    def test_oversized_chunked_non_json_and_malformed_headers_rejected(self):
        for headers, expected in (
            ({"Content-Length": "5000"}, 413),
            ({"Transfer-Encoding": "chunked"}, 413),
            ({"Content-Type": "text/plain"}, 415),
            ({"Content-Length": "0" * 5000}, 413),
            ({"Content-Length": "-1"}, 413),
            ({"X-Demo-CSRF": "é"}, 403),
        ):
            self.assertEqual(self.post(headers=headers)[0], expected)

    def test_arbitrary_paths_and_live_or_legacy_routes_absent(self):
        for path in (
            "/../README.md",
            "/api/bootstrap?tenant=other",
            "/cloud",
            "/api/credentials",
            "/style.css?x=1",
        ):
            self.assertEqual(self.call("GET", path)[0], 404)
        self.assertEqual(self.post(path="/api/run")[0], 404)

    def test_safe_rendering_and_logical_layout(self):
        with self.assertRaises(ValueError):
            DemoServer(("0.0.0.0", 8765))
        root = Path(__file__).resolve().parents[2]
        script = (root / "demo/ui/app.js").read_text()
        self.assertNotIn("innerHTML", script)
        self.assertIn("textContent", script)
        self.assertIn("ArrowLeft", script)
        self.assertIn("item.dir = 'ltr'", script)
        self.assertNotIn("localStorage", script)
        self.assertIn("JSON.stringify(selectedReport", script)
        css = (root / "demo/ui/style.css").read_text()
        for invalid in (
            "margin-left",
            "margin-right",
            "padding-left",
            "padding-right",
            "text-align:left",
        ):
            self.assertNotIn(invalid, css)
        self.assertIn("unicode-bidi:isolate", css)

    def test_localization_catalog_has_separate_complete_language_views(self):
        status, _, body = self.call("GET", "/i18n.json")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(set(data["en"]), set(data["ar"]))
        self.assertEqual(data["en"]["send"], "Send")
        self.assertEqual(data["ar"]["send"], "إرسال")
        self.assertNotIn("· Send", data["ar"]["send"])


class HTTPBoundariesTests(unittest.TestCase):
    def setUp(self):
        self.received = []
        received = self.received

        class Endpoint(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                received.append(self.path)
                self.rfile.read(int(self.headers["Content-Length"]))
                if self.path == "/redirect":
                    self.send_response(307)
                    self.send_header("Location", "/target")
                    self.end_headers()
                else:
                    body = (
                        b'"' + b"x" * 65537 + b'"'
                        if self.path == "/oversized"
                        else b'{"ok":true}'
                    )
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Endpoint)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def test_no_redirect_authentication_forwarding(self):
        with self.assertRaises(urllib.error.HTTPError):
            _post_json(
                self.base + "/redirect", {}, 2, {"Authorization": "Bearer dummy"}
            )
        self.assertEqual(self.received, ["/redirect"])

    def test_oversized_http_response_rejected(self):
        with self.assertRaises(ValueError):
            _post_json(self.base + "/oversized", {}, 2)

    def test_ambient_proxy_is_not_used(self):
        with mock.patch.dict(
            "os.environ",
            {
                "HTTP_PROXY": "http://127.0.0.1:1",
                "http_proxy": "http://127.0.0.1:1",
                "NO_PROXY": "",
                "no_proxy": "",
            },
        ):
            self.assertEqual(_post_json(self.base + "/valid", {}, 2), {"ok": True})


if __name__ == "__main__":
    unittest.main()
