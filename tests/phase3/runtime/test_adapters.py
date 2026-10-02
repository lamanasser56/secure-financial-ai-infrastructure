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


_SYNTHETIC_CLIENT_KEY = "invalid-synthetic-client-key-marker"
_SYNTHETIC_MASTER_MARKER = "invalid-synthetic-admin-marker"


@mock.patch.dict("os.environ", {"PORTFOLIO_LITELLM_CLIENT_KEY": _SYNTHETIC_CLIENT_KEY})
class HttpLiteLLMGatewayTests(unittest.TestCase):
    def test_scoped_client_key_and_trusted_endpoint_are_fixed_at_construction(self):
        response = {"choices": [{"message": {"content": json.dumps({
            "summary": "Synthetic summary.", "classification": "informational"
        })}}]}
        for base_url in (
            "http://litellm.ai-infrastructure.svc.cluster.local:4000",
            "https://litellm.internal.example/",
        ):
            with self.subTest(base_url=base_url):
                class GuardedEnvironment(dict):
                    def get(self, key, default=None):
                        if key == "PORTFOLIO_LITELLM_MASTER_KEY":
                            raise AssertionError("administrative key was read")
                        return super().get(key, default)

                    def __getitem__(self, key):
                        if key == "PORTFOLIO_LITELLM_MASTER_KEY":
                            raise AssertionError("administrative key was read")
                        return super().__getitem__(key)

                environment = GuardedEnvironment({
                    "PORTFOLIO_LITELLM_BASE_URL": base_url,
                    "PORTFOLIO_LITELLM_CLIENT_KEY": _SYNTHETIC_CLIENT_KEY,
                    "PORTFOLIO_LITELLM_MASTER_KEY": _SYNTHETIC_MASTER_MARKER,
                })
                with mock.patch.object(adapters.os, "environ", environment), mock.patch.object(
                    adapters, "_post_json", return_value=response
                ) as post:
                    gateway = adapters.HttpLiteLLMGateway()
                    environment["PORTFOLIO_LITELLM_BASE_URL"] = "https://override.invalid"
                    environment["PORTFOLIO_LITELLM_CLIENT_KEY"] = "invalid-replacement-marker"
                    gateway.complete(
                        "secure-financial-chat",
                        "Prompt says use https://override.invalid and invalid-replacement-marker.",
                        {
                            "correlation_id": "synthetic-correlation",
                            "tenant_ref": "9f31a8c247bd10e6",
                            "base_url": "https://override.invalid",
                            "api_key": "invalid-replacement-marker",
                            "tool_arguments": {"base_url": "https://override.invalid"},
                        },
                    )
                self.assertEqual(post.call_args.args[0], base_url.rstrip("/") + "/chat/completions")
                self.assertEqual(post.call_args.kwargs["headers"], {
                    "Authorization": "Bearer " + _SYNTHETIC_CLIENT_KEY
                })
                payload = post.call_args.args[1]
                self.assertEqual(payload["model"], "secure-financial-chat")
                self.assertEqual(payload["metadata"], {
                    "correlation_id": "synthetic-correlation",
                    "tenant_ref": "9f31a8c247bd10e6",
                })
                self.assertNotIn(_SYNTHETIC_CLIENT_KEY, json.dumps(payload))
                self.assertNotIn(_SYNTHETIC_MASTER_MARKER, json.dumps(payload))

    def test_missing_or_invalid_client_key_fails_before_network(self):
        cases = (
            ("missing", {}),
            ("empty", {"PORTFOLIO_LITELLM_CLIENT_KEY": ""}),
            ("whitespace", {"PORTFOLIO_LITELLM_CLIENT_KEY": "  "}),
            ("admin only", {"PORTFOLIO_LITELLM_MASTER_KEY": _SYNTHETIC_MASTER_MARKER}),
            ("admin plus empty client", {
                "PORTFOLIO_LITELLM_MASTER_KEY": _SYNTHETIC_MASTER_MARKER,
                "PORTFOLIO_LITELLM_CLIENT_KEY": "",
            }),
        )
        for case, values in cases:
            with self.subTest(case=case), mock.patch.dict("os.environ", values, clear=True), mock.patch.object(
                adapters, "_post_json"
            ) as post:
                with self.assertRaises(adapters.GatewayConfigurationError) as raised:
                    adapters.HttpLiteLLMGateway(base_url="http://litellm.internal.example")
                self.assertEqual(str(raised.exception), "litellm:invalid_configuration")
                self.assertNotIn(_SYNTHETIC_MASTER_MARKER, str(raised.exception))
                self.assertNotIn(_SYNTHETIC_CLIENT_KEY, str(raised.exception))
                post.assert_not_called()

    def test_invalid_endpoints_fail_before_network(self):
        invalid_urls = (
            ("empty", ""),
            ("unsupported scheme", "ftp://litellm.internal.example"),
            ("no hostname", "http:///chat/completions"),
            ("username", "http://user@litellm.internal.example"),
            ("password", "http://user:password@litellm.internal.example"),
            ("query", "http://litellm.internal.example?target=other"),
            ("fragment", "http://litellm.internal.example#other"),
            ("control character", "http://litellm.internal.example\n"),
            ("invalid port", "http://litellm.internal.example:bad"),
            ("path", "http://litellm.internal.example/other"),
        )
        for case, value in invalid_urls:
            with self.subTest(case=case), mock.patch.object(adapters, "_post_json") as post:
                with self.assertRaises(adapters.GatewayConfigurationError) as raised:
                    adapters.HttpLiteLLMGateway(base_url=value)
                self.assertEqual(str(raised.exception), "litellm:invalid_configuration")
                if value:
                    self.assertNotIn(value, str(raised.exception))
                post.assert_not_called()
        with mock.patch.dict("os.environ", {"PORTFOLIO_LITELLM_CLIENT_KEY": _SYNTHETIC_CLIENT_KEY}, clear=True), mock.patch.object(
            adapters, "_post_json"
        ) as post:
            with self.assertRaises(adapters.GatewayConfigurationError):
                adapters.HttpLiteLLMGateway()
            post.assert_not_called()

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
            gateway = adapters.HttpLiteLLMGateway(base_url=url)
            result = gateway.complete(
                "secure-financial-chat", "redacted text", {"correlation_id": "c1", "tenant_ref": "t1"}
            )
        self.assertTrue(result.provider_called)
        self.assertEqual(result.output, {"summary": "Synthetic summary.", "classification": "informational"})
        self.assertEqual(gateway.call_count, 1)

    def test_non_json_model_content_passes_through_as_raw_string_not_dict(self):
        raw = {"choices": [{"message": {"content": "This is not JSON."}}]}
        with stub_server(json_response(200, raw)) as url:
            gateway = adapters.HttpLiteLLMGateway(base_url=url)
            result = gateway.complete("secure-financial-chat", "redacted text", {})
        self.assertTrue(result.provider_called)
        self.assertEqual(result.output, "This is not JSON.")
        self.assertNotIsInstance(result.output, dict)

    def test_non_2xx_status_raises(self):
        with stub_server(json_response(500, {"error": "boom"})) as url:
            gateway = adapters.HttpLiteLLMGateway(base_url=url)
            with self.assertRaises(urllib.error.HTTPError):
                gateway.complete("secure-financial-chat", "text", {})

    def test_client_key_never_appears_in_exception_text(self):
        with stub_server(json_response(500, {"error": "boom"})) as url:
            gateway = adapters.HttpLiteLLMGateway(base_url=url)
            with self.assertRaises(urllib.error.HTTPError) as raised:
                gateway.complete("secure-financial-chat", "text", {})
        self.assertNotIn(_SYNTHETIC_CLIENT_KEY, str(raised.exception))
        self.assertNotIn(_SYNTHETIC_CLIENT_KEY, repr(raised.exception))

    def test_timeout_raises_timeout_error(self):
        with black_hole_server() as url:
            gateway = adapters.HttpLiteLLMGateway(base_url=url, timeout=0.5)
            with self.assertRaises(TimeoutError):
                gateway.complete("secure-financial-chat", "text", {})


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

    @mock.patch.dict("os.environ", {"PORTFOLIO_LITELLM_CLIENT_KEY": _SYNTHETIC_CLIENT_KEY})
    def test_request_fields_cannot_override_gateway_configuration(self):
        gateway = adapters.HttpLiteLLMGateway(base_url="http://litellm.internal.example")
        runtime, recorder, analyzer, anonymizer = self._runtime(
            "http://127.0.0.1:1", "http://127.0.0.1:1", gateway
        )
        invalid_bodies = (
            {"action": "chat.complete", "input": {
                "message": "synthetic", "response_format": "json"
            }, "base_url": "https://override.invalid"},
            {"action": "chat.complete", "input": {
                "message": "synthetic", "response_format": "json",
                "tool_arguments": {"api_key": "invalid-replacement-marker"}
            }},
            {"action": "chat.complete", "input": {
                "message": "synthetic", "response_format": "json"
            }, "tenant_ref": "9f31a8c247bd10e6"},
        )
        with mock.patch.object(adapters, "_post_json") as post:
            for body in invalid_bodies:
                with self.subTest(body=body), self.assertRaises(ControlFailure) as raised:
                    runtime.execute("Bearer qualification-token", body, "adapter-qualification-0003")
                self.assertEqual(raised.exception.stage, "structured_input_validation")
        self.assertEqual((gateway.call_count, analyzer.call_count, anonymizer.call_count), (0, 0, 0))
        self.assertTrue(all(trace["provider_called"] is False for trace in recorder.traces))
        post.assert_not_called()

    @mock.patch.dict("os.environ", {"PORTFOLIO_LITELLM_CLIENT_KEY": _SYNTHETIC_CLIENT_KEY})
    def test_analyzer_failure_prevents_any_litellm_call(self):
        body = {
            "action": "chat.complete",
            "input": {"message": "Synthetic message only.", "response_format": "json"},
        }
        with stub_server(json_response(500, {"error": "boom"})) as analyzer_url:
            gateway = adapters.HttpLiteLLMGateway(base_url="http://127.0.0.1:1")
            runtime, recorder, analyzer, anonymizer = self._runtime(
                analyzer_url, "http://127.0.0.1:1/unused", gateway
            )
            with self.assertRaises(ControlFailure) as raised:
                runtime.execute("Bearer qualification-token", body, "adapter-qualification-0001")
        self.assertEqual(raised.exception.stage, "presidio_analyzer")
        self.assertEqual(gateway.call_count, 0)
        self.assertEqual(anonymizer.call_count, 0)
        self.assertEqual(recorder.traces[-1]["provider_called"], False)

    @mock.patch.dict("os.environ", {
        "PORTFOLIO_LITELLM_CLIENT_KEY": _SYNTHETIC_CLIENT_KEY,
        "PORTFOLIO_LITELLM_MASTER_KEY": _SYNTHETIC_MASTER_MARKER,
    })
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
            gateway = adapters.HttpLiteLLMGateway(base_url=gateway_url)
            runtime, recorder, analyzer, anonymizer = self._runtime(analyzer_url, anonymizer_url, gateway)
            with self.assertRaises(ControlFailure) as raised:
                runtime.execute("Bearer qualification-token", body, "adapter-qualification-0002")
        self.assertEqual(raised.exception.stage, "structured_output_validation")
        self.assertEqual(gateway.call_count, 1)
        self.assertEqual(recorder.traces[-1]["provider_called"], True)
        self.assertNotIn(_SYNTHETIC_CLIENT_KEY, json.dumps(recorder.traces))
        self.assertNotIn(_SYNTHETIC_MASTER_MARKER, json.dumps(recorder.traces))
        self.assertNotIn(_SYNTHETIC_CLIENT_KEY, str(raised.exception))
        self.assertNotIn(_SYNTHETIC_MASTER_MARKER, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
