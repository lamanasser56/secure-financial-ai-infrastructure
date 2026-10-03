import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest
from unittest import mock
import urllib.error

from runtime.agents.web import DemoServer
from runtime.phase3.adapters import _post_json


class PrivateUITests(unittest.TestCase):
    def setUp(self):
        self.server = DemoServer(("127.0.0.1", 0))
        self.origin = self.server.origin

    def tearDown(self):
        self.server.server_close()

    def call(self, method, path, body=None, headers=None):
        outcomes = []

        def client():
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.server.server_port, timeout=5
            )
            try:
                connection.request(method, path, body=body, headers=headers or {})
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

    def post(self, payload=None, headers=None):
        standard = {
            "Origin": self.origin,
            "X-Demo-CSRF": self.server.csrf,
            "Content-Type": "application/json",
        }
        if headers:
            standard.update(headers)
        payload = payload or {
            "agent": "financial",
            "period": "2026-01",
            "scenario_id": None,
        }
        return self.call("POST", "/api/run", json.dumps(payload), standard)

    def test_private_assets_and_security_headers(self):
        status, headers, body = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn('dir="ltr"', body.decode())
        self.assertIn('lang="en"', body.decode())
        self.assertNotIn('id="language"', body.decode())
        self.assertNotRegex(body.decode(), r"[\u0600-\u06ff]")
        self.assertIn('role="tablist"', body.decode())
        self.assertIn('aria-live="polite"', body.decode())
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_bootstrap_contains_no_gateway_or_identity_credential(self):
        status, _, body = self.call("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        value = json.loads(body)
        self.assertEqual(
            set(value), {"csrf", "mode", "authentication", "synthetic_only"}
        )
        self.assertEqual(value["authentication"], "simulated")
        for _, auth in self.server.agents.values():
            self.assertFalse(
                auth in body.decode(),
                "Private simulated credential unexpectedly present",
            )

    def test_ui_financial_and_infrastructure_complete(self):
        for payload in (
            {
                "agent": "financial",
                "period": "2026-01",
                "scenario_id": None,
            },
            {
                "agent": "infrastructure",
                "period": None,
                "scenario_id": "cluster-version",
            },
        ):
            status, _, body = self.post(payload)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["status"], "completed", body.decode())
            self.assertEqual(json.loads(body)["mode"], "offline_simulation")

    def test_missing_period_clarifies(self):
        status, _, body = self.post(
            {
                "agent": "financial",
                "period": None,
                "scenario_id": None,
            }
        )
        self.assertEqual(status, 200)
        value = json.loads(body)
        self.assertEqual(value["status"], "clarification_required")
        self.assertEqual((value["model_requests"], value["tool_executions"]), (0, 0))
        self.assertNotIn("facts", value)
        self.assertNotIn("financial", value["presentation"])

    def test_report_preserves_raw_minor_units_and_truthful_usage(self):
        status, _, body = self.post()
        self.assertEqual(status, 200)
        value = json.loads(body)
        self.assertEqual(value["facts"][0]["result"]["total_minor_units"], 24000)
        finance = value["presentation"]["financial"]
        self.assertEqual(finance["total"], "SAR 240.00")
        self.assertEqual(
            [c["amount"] for c in finance["categories"]], ["SAR 200.00", "SAR 40.00"]
        )
        usage = value["presentation"]["usage"]
        self.assertEqual(usage["simulated_model_requests"], 3)
        self.assertEqual(usage["external_provider_calls"], 0)
        self.assertIsNone(usage["token_usage"])
        self.assertIsNone(usage["cost"])
        self.assertNotIn("csrf", value)
        self.assertNotRegex(body.decode(), r"[\u0600-\u06ff]")

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

    def test_missing_origin_and_wrong_csrf_are_rejected(self):
        self.assertEqual(
            self.call(
                "POST",
                "/api/run",
                body="{}",
                headers={
                    "Content-Type": "application/json",
                    "X-Demo-CSRF": self.server.csrf,
                },
            )[0],
            403,
        )
        self.assertEqual(self.post(headers={"X-Demo-CSRF": "wrong"})[0], 403)

    def test_request_identity_headers_and_payload_cannot_override_context(self):
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
            "gateway_url",
            "model",
            "credential",
            "message",
            "language",
        ):
            payload = {
                "agent": "financial",
                "period": "2026-01",
                "scenario_id": None,
                key: "untrusted",
            }
            self.assertEqual(self.post(payload)[0], 400)

    def test_oversized_chunked_and_non_json_bodies_rejected(self):
        self.assertEqual(self.post(headers={"Content-Length": "5000"})[0], 413)
        self.assertEqual(self.post(headers={"Transfer-Encoding": "chunked"})[0], 413)
        self.assertEqual(self.post(headers={"Content-Type": "text/plain"})[0], 415)

    def test_malformed_numeric_and_non_ascii_headers_are_sanitized(self):
        self.assertEqual(self.post(headers={"Content-Length": "0" * 5000})[0], 413)
        self.assertEqual(self.post(headers={"Content-Length": "-1"})[0], 413)
        self.assertEqual(self.post(headers={"X-Demo-CSRF": "é"})[0], 403)

    def test_arbitrary_paths_query_strings_and_cloud_routes_absent(self):
        for path in (
            "/../README.md",
            "/api/bootstrap?tenant=other",
            "/cloud",
            "/api/credentials",
            "/style.css?x=1",
        ):
            self.assertEqual(self.call("GET", path)[0], 404)

    def test_public_binding_and_unsafe_rendering_absent(self):
        with self.assertRaises(ValueError):
            DemoServer(("0.0.0.0", 8765))
        script = (Path(__file__).resolve().parents[2] / "demo/ui/app.js").read_text()
        self.assertNotIn("innerHTML", script)
        self.assertIn("textContent", script)
        self.assertIn("ArrowLeft", script)
        self.assertNotIn("localStorage", script)


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
