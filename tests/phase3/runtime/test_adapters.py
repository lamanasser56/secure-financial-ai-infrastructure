import contextlib
import json
import socket
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from runtime.phase3 import adapters
from runtime.phase3.mocks import (
    MockAuthenticator,
    MockAuthorizer,
    MockPolicyEngine,
    MockTenantResolver,
    MockTraceSink,
    Recorder,
)
from runtime.phase3.trusted_runtime import ControlFailure, TrustedRuntime


class _StubHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        status, body = self.server.response_provider()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


@contextlib.contextmanager
def stub_server(response_provider):
    server = HTTPServer(("127.0.0.1", 0), _StubHandler)
    server.response_provider = response_provider
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@contextlib.contextmanager
def black_hole_server():
    """Accepts connections but never responds, to trigger a client-side timeout."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    stop = threading.Event()
    held: list[socket.socket] = []

    def accept_loop():
        listener.settimeout(0.5)
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
                held.append(conn)
            except socket.timeout:
                continue

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        stop.set()
        thread.join(timeout=5)
        for conn in held:
            conn.close()
        listener.close()


def json_response(status, payload):
    return lambda: (status, json.dumps(payload).encode("utf-8"))


def raw_response(status, body: bytes):
    return lambda: (status, body)


class HttpPresidioAnalyzerTests(unittest.TestCase):
    def test_projects_extra_fields_to_closed_shape(self):
        raw = [
            {
                "entity_type": "EMAIL_ADDRESS",
                "start": 0,
                "end": 4,
                "score": 0.9,
                "analysis_explanation": {"unexpected": "field"},
                "recognition_metadata": {"recognizer_name": "EmailRecognizer"},
            }
        ]
        with stub_server(json_response(200, raw)) as url:
            analyzer = adapters.HttpPresidioAnalyzer(url=url)
            result = analyzer.analyze("test@example.com")
        self.assertEqual(result, [{"entity_type": "EMAIL_ADDRESS", "start": 0, "end": 4, "score": 0.9}])
        self.assertEqual(analyzer.call_count, 1)

    def test_non_2xx_status_raises(self):
        with stub_server(json_response(500, {"error": "boom"})) as url:
            analyzer = adapters.HttpPresidioAnalyzer(url=url)
            with self.assertRaises(urllib.error.HTTPError):
                analyzer.analyze("text")

    def test_malformed_json_body_raises(self):
        with stub_server(raw_response(200, b"not json")) as url:
            analyzer = adapters.HttpPresidioAnalyzer(url=url)
            with self.assertRaises(json.JSONDecodeError):
                analyzer.analyze("text")

    def test_malformed_result_shape_raises(self):
        raw = [{"entity_type": "EMAIL_ADDRESS", "start": 0, "end": 4}]  # missing "score"
        with stub_server(json_response(200, raw)) as url:
            analyzer = adapters.HttpPresidioAnalyzer(url=url)
            with self.assertRaises(KeyError):
                analyzer.analyze("text")

    def test_timeout_raises_timeout_error(self):
        with black_hole_server() as url:
            analyzer = adapters.HttpPresidioAnalyzer(url=url, timeout=0.5)
            with self.assertRaises(TimeoutError):
                analyzer.analyze("text")


class HttpPresidioAnonymizerTests(unittest.TestCase):
    def test_projects_extra_fields_to_closed_shape(self):
        raw = {"text": "[REDACTED]", "items": [{"operator": "replace"}]}
        with stub_server(json_response(200, raw)) as url:
            anonymizer = adapters.HttpPresidioAnonymizer(url=url)
            result = anonymizer.anonymize(
                "test@example.com",
                [{"entity_type": "EMAIL_ADDRESS", "start": 0, "end": 16, "score": 0.9}],
            )
        self.assertEqual(result, {"text": "[REDACTED]"})
        self.assertEqual(anonymizer.call_count, 1)

    def test_non_2xx_status_raises(self):
        with stub_server(json_response(503, {"error": "unavailable"})) as url:
            anonymizer = adapters.HttpPresidioAnonymizer(url=url)
            with self.assertRaises(urllib.error.HTTPError):
                anonymizer.anonymize("text", [])

    def test_missing_text_field_raises(self):
        with stub_server(json_response(200, {"items": []})) as url:
            anonymizer = adapters.HttpPresidioAnonymizer(url=url)
            with self.assertRaises(KeyError):
                anonymizer.anonymize("text", [])

    def test_timeout_raises_timeout_error(self):
        with black_hole_server() as url:
            anonymizer = adapters.HttpPresidioAnonymizer(url=url, timeout=0.5)
            with self.assertRaises(TimeoutError):
                anonymizer.anonymize("text", [])


_SYNTHETIC_MASTER_KEY = "synthetic-test-master-key-marker"


@mock.patch.dict("os.environ", {"Portfolio_LITELLM_MASTER_KEY": _SYNTHETIC_MASTER_KEY})
class HttpLiteLLMGatewayTests(unittest.TestCase):
    def test_contract_conforming_model_output_is_parsed(self):
        raw = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"summary": "Synthetic summary.", "classification": "informational"}
                        )
                    }
                }
            ]
        }
        with stub_server(json_response(200, raw)) as url:
            gateway = adapters.HttpLiteLLMGateway(url=url)
            result = gateway.complete(
                "ai-platformroved-chat", "redacted text", {"correlation_id": "c1", "tenant_ref": "t1"}
            )
        self.assertTrue(result.provider_called)
        self.assertEqual(result.output, {"summary": "Synthetic summary.", "classification": "informational"})
        self.assertEqual(gateway.call_count, 1)

    def test_non_json_model_content_passes_through_as_raw_string_not_dict(self):
        raw = {"choices": [{"message": {"content": "This is not JSON."}}]}
        with stub_server(json_response(200, raw)) as url:
            gateway = adapters.HttpLiteLLMGateway(url=url)
            result = gateway.complete("ai-platformroved-chat", "redacted text", {})
        self.assertTrue(result.provider_called)
        self.assertEqual(result.output, "This is not JSON.")
        self.assertNotIsInstance(result.output, dict)

    def test_non_2xx_status_raises(self):
        with stub_server(json_response(500, {"error": "boom"})) as url:
            gateway = adapters.HttpLiteLLMGateway(url=url)
            with self.assertRaises(urllib.error.HTTPError):
                gateway.complete("ai-platformroved-chat", "text", {})

    def test_master_key_never_appears_in_exception_text(self):
        with stub_server(json_response(500, {"error": "boom"})) as url:
            gateway = adapters.HttpLiteLLMGateway(url=url)
            with self.assertRaises(urllib.error.HTTPError) as raised:
                gateway.complete("ai-platformroved-chat", "text", {})
        self.assertNotIn(_SYNTHETIC_MASTER_KEY, str(raised.exception))
        self.assertNotIn(_SYNTHETIC_MASTER_KEY, repr(raised.exception))

    def test_timeout_raises_timeout_error(self):
        with black_hole_server() as url:
            gateway = adapters.HttpLiteLLMGateway(url=url, timeout=0.5)
            with self.assertRaises(TimeoutError):
                gateway.complete("ai-platformroved-chat", "text", {})


class HttpAdapterIntegrationWithTrustedRuntimeTests(unittest.TestCase):
    def _runtime(self, analyzer_url, anonymizer_url, gateway):
        recorder = Recorder()
        analyzer = adapters.HttpPresidioAnalyzer(url=analyzer_url)
        anonymizer = adapters.HttpPresidioAnonymizer(url=anonymizer_url)
        runtime = TrustedRuntime(
            MockAuthenticator(recorder),
            MockTenantResolver(recorder),
            MockAuthorizer(recorder),
            MockPolicyEngine(recorder),
            analyzer,
            anonymizer,
            gateway,
            MockTraceSink(recorder),
        )
        return runtime, recorder, analyzer, anonymizer

    def test_analyzer_failure_prevents_any_litellm_call(self):
        body = {
            "action": "chat.complete",
            "input": {"message": "Synthetic message only.", "response_format": "json"},
        }
        with stub_server(json_response(500, {"error": "boom"})) as analyzer_url:
            gateway = adapters.HttpLiteLLMGateway(url="http://127.0.0.1:1/unused")
            runtime, recorder, analyzer, anonymizer = self._runtime(
                analyzer_url, "http://127.0.0.1:1/unused", gateway
            )
            with self.assertRaises(ControlFailure) as raised:
                runtime.execute("Bearer qualification-token", body, "adapter-qualification-0001")
        self.assertEqual(raised.exception.stage, "presidio_analyzer")
        self.assertEqual(gateway.call_count, 0)
        self.assertEqual(anonymizer.call_count, 0)
        self.assertEqual(recorder.traces[-1]["provider_called"], False)

    @mock.patch.dict("os.environ", {"Portfolio_LITELLM_MASTER_KEY": _SYNTHETIC_MASTER_KEY})
    def test_litellm_non_contract_output_fails_closed_at_output_validation(self):
        body = {
            "action": "chat.complete",
            "input": {"message": "Synthetic message only.", "response_format": "json"},
        }
        analyzer_body = json.dumps([]).encode("utf-8")
        anonymizer_raw = {"text": "Synthetic message only."}
        litellm_raw = {"choices": [{"message": {"content": "not valid json"}}]}
        with stub_server(raw_response(200, analyzer_body)) as analyzer_url, stub_server(
            json_response(200, anonymizer_raw)
        ) as anonymizer_url, stub_server(json_response(200, litellm_raw)) as gateway_url:
            gateway = adapters.HttpLiteLLMGateway(url=gateway_url)
            runtime, recorder, analyzer, anonymizer = self._runtime(analyzer_url, anonymizer_url, gateway)
            with self.assertRaises(ControlFailure) as raised:
                runtime.execute("Bearer qualification-token", body, "adapter-qualification-0002")
        self.assertEqual(raised.exception.stage, "structured_output_validation")
        self.assertEqual(gateway.call_count, 1)
        self.assertEqual(recorder.traces[-1]["provider_called"], True)


if __name__ == "__main__":
    unittest.main()
