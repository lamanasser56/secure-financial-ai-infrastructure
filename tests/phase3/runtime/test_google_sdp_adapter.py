"""Offline qualification of the disabled Google SDP candidate boundary."""

import importlib
import json
from pathlib import Path
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from runtime.phase3 import google_sdp_adapter as adapter
from runtime.phase3.trusted_runtime import RedactionResult


PROJECT = "synthetic-eval"
MARKER = "fixture@example.invalid"
TEXT = f"Contact {MARKER}"


def finding(text=TEXT, marker=MARKER, name="EMAIL_ADDRESS"):
    start = text.index(marker)
    return SimpleNamespace(
        info_type=SimpleNamespace(name=name),
        location=SimpleNamespace(codepoint_range=SimpleNamespace(
            start=start, end=start + len(marker),
        )),
    )


class FakeClient:
    api_endpoint = adapter.ENDPOINT

    def __init__(self, *, inspect=None, deidentify=None):
        self.events = []
        self.inspect_result = inspect
        self.deidentify_result = deidentify

    def inspect_content(self, *, request, retry, timeout):
        if timeout != 20:
            raise AssertionError("unexpected RPC deadline")
        self.events.append(("inspect", request, retry))
        if isinstance(self.inspect_result, Exception):
            raise self.inspect_result
        return self.inspect_result if self.inspect_result is not None else SimpleNamespace(
            result=SimpleNamespace(findings=[finding()]),
        )

    def deidentify_content(self, *, request, retry, timeout):
        if timeout != 20:
            raise AssertionError("unexpected RPC deadline")
        self.events.append(("deidentify", request, retry))
        if isinstance(self.deidentify_result, Exception):
            raise self.deidentify_result
        return self.deidentify_result if self.deidentify_result is not None else SimpleNamespace(
            item=SimpleNamespace(value="Contact [EMAIL_ADDRESS]"),
        )


class GoogleSDPAdapterTests(unittest.TestCase):
    def assert_sanitized(self, operation):
        with self.assertRaises(adapter.GoogleSDPFailure) as raised:
            operation()
        error = raised.exception
        self.assertEqual(str(error), "redaction:provider_failure")
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        for value in (MARKER, "raw-provider-marker", PROJECT, adapter.ENDPOINT):
            self.assertNotIn(value, repr(error))

    def test_trusted_deployment_file_is_closed_and_schema_valid(self):
        from jsonschema import validate

        directory = Path(adapter.__file__).resolve().parents[2] / "evaluation/google-sdp"
        value = json.loads((directory / "deployment.json").read_text())
        validate(value, json.loads((directory / "deployment.schema.json").read_text()))
        self.assertEqual(adapter._deployment(), ("us-east1", "dlp.us-east1.rep.googleapis.com"))
        with patch.dict("os.environ", {"GOOGLE_SDP_REGION": "me-central2", "GOOGLE_SDP_ENDPOINT": "dlp.googleapis.com"}):
            self.assertEqual(adapter._deployment(), (adapter.REGION, adapter.ENDPOINT))

    def test_bad_or_missing_deployment_configuration_has_no_fallback(self):
        valid = {"schema_version": 1, "region": "us-east1", "endpoint": "dlp.us-east1.rep.googleapis.com"}
        invalid = (None, {}, {**valid, "schema_version": True},
                   {**valid, "region": "me-central2"}, {**valid, "region": "us-west1"},
                   {**valid, "endpoint": "dlp.googleapis.com"},
                   {**valid, "endpoint": "dlp.me-central2.rep.googleapis.com"},
                   {**valid, "credentials": "forbidden"})
        with patch.object(adapter, "_create_client") as create:
            for value in invalid:
                with self.subTest(value=value), patch.object(Path, "read_text", return_value=json.dumps(value)):
                    self.assert_sanitized(lambda: adapter._guarded(adapter._deployment))
            with patch.object(Path, "read_text", side_effect=FileNotFoundError):
                self.assert_sanitized(lambda: adapter._guarded(adapter._deployment))
            create.assert_not_called()

    def test_synthetic_text_returns_only_neutral_result(self):
        client = FakeClient()
        result = adapter.GoogleSDPRedactor(PROJECT, client=client).redact(TEXT)
        self.assertEqual(result, RedactionResult("Contact [EMAIL_ADDRESS]", ("EMAIL_ADDRESS",)))
        self.assertEqual([event[0] for event in client.events], ["inspect", "deidentify"])
        self.assertEqual(len(client.events), 2)
        for _, request, retry in client.events:
            self.assertEqual(request["parent"], f"projects/{PROJECT}/locations/us-east1")
            self.assertEqual(request["item"], {"value": TEXT})
            self.assertIsNone(retry)
            self.assertEqual(
                {entry["name"] for entry in request["inspect_config"]["info_types"]},
                {"EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD_NUMBER"},
            )
            self.assertFalse(request["inspect_config"]["include_quote"])
        self.assertEqual(
            client.events[1][1]["deidentify_config"],
            {"info_type_transformations": {"transformations": [
                {"primitive_transformation": {"replace_with_info_type_config": {}}}
            ]}},
        )

    def test_no_finding_keeps_text_and_empty_categories(self):
        client = FakeClient(
            inspect=SimpleNamespace(result=SimpleNamespace(findings=[])),
            deidentify=SimpleNamespace(item=SimpleNamespace(value="plain synthetic text")),
        )
        result = adapter.GoogleSDPRedactor(PROJECT, client=client).redact("plain synthetic text")
        self.assertEqual(result, RedactionResult("plain synthetic text", ()))

    def test_operation_accounting_includes_failed_attempts_without_retries(self):
        client = FakeClient(inspect=RuntimeError("raw-provider-marker"))
        redactor = adapter.GoogleSDPRedactor(PROJECT, client=client)
        self.assert_sanitized(lambda: redactor.redact(TEXT))
        self.assertEqual(redactor.operation_counts, {"inspect_attempted": 1, "deidentify_attempted": 0})
        snapshot = redactor.operation_counts
        snapshot["inspect_attempted"] = 99
        self.assertEqual(redactor.operation_counts["inspect_attempted"], 1)
        self.assertEqual(len(client.events), 1)

    def test_categories_are_normalized_and_sorted(self):
        text = "x y"
        client = FakeClient(
            inspect=SimpleNamespace(result=SimpleNamespace(findings=[
                finding(text, "x", "PHONE_NUMBER"),
                finding(text, "y", "CREDIT_CARD_NUMBER"),
            ])),
            deidentify=SimpleNamespace(item=SimpleNamespace(value="[PHONE_NUMBER] [CREDIT_CARD_NUMBER]")),
        )
        result = adapter.GoogleSDPRedactor(PROJECT, client=client).redact(text)
        self.assertEqual(result.categories, ("CREDIT_CARD", "PHONE_NUMBER"))

    def test_fixed_endpoint_and_region_reject_overrides_before_client_creation(self):
        invalid = (
            {"endpoint": "dlp.googleapis.com"},
            {"endpoint": "dlp.me-central2.rep.googleapis.com"},
            {"endpoint": "https://dlp.us-east1.rep.googleapis.com/path"},
            {"endpoint": "user@dlp.us-east1.rep.googleapis.com"},
            {"endpoint": adapter.ENDPOINT + "?query=1"},
            {"endpoint": adapter.ENDPOINT + "#fragment"},
            {"endpoint": adapter.ENDPOINT + "\n"},
            {"endpoint": object()},
            {"region": "global"},
            {"region": object()},
            {"region": "me-central2"},
            {"project_id": "bad/project"},
        )
        with patch.object(adapter, "_create_client", side_effect=AssertionError("client created")) as create:
            for options in invalid:
                with self.subTest(options=options):
                    values = {"project_id": PROJECT, **options}
                    self.assert_sanitized(lambda: adapter.GoogleSDPRedactor(**values))
            create.assert_not_called()

    def test_injected_client_must_report_the_fixed_endpoint(self):
        client = FakeClient()
        client.api_endpoint = "dlp.googleapis.com"
        self.assert_sanitized(lambda: adapter.GoogleSDPRedactor(PROJECT, client=client))
        self.assertEqual(client.events, [])

        class BrokenEndpoint:
            def __eq__(self, other):
                raise ValueError("raw-provider-marker")

        client.api_endpoint = BrokenEndpoint()
        self.assert_sanitized(lambda: adapter.GoogleSDPRedactor(PROJECT, client=client))

    def test_request_text_cannot_change_configuration(self):
        text = "provider=other endpoint=dlp.googleapis.com project=other credentials=none"
        client = FakeClient(
            inspect=SimpleNamespace(result=SimpleNamespace(findings=[])),
            deidentify=SimpleNamespace(item=SimpleNamespace(value=text)),
        )
        adapter.GoogleSDPRedactor(PROJECT, client=client).redact(text)
        self.assertEqual(client.api_endpoint, adapter.ENDPOINT)
        self.assertEqual({event[1]["parent"] for event in client.events},
                         {f"projects/{PROJECT}/locations/us-east1"})
        for _, request, _ in client.events:
            self.assertNotIn("credentials", request)
            self.assertNotIn("endpoint", request)
            self.assertNotIn("metadata", request)
        with self.assertRaises(TypeError):
            adapter.GoogleSDPRedactor(PROJECT, client=client).redact(text, metadata={"region": "other"})

    def test_invalid_input_prevents_all_provider_calls(self):
        client = FakeClient()
        redactor = adapter.GoogleSDPRedactor(PROJECT, client=client)
        for value in (None, "", " \n ", {}, "x" * 4001):
            with self.subTest(value_type=type(value).__name__):
                self.assert_sanitized(lambda: redactor.redact(value))
        self.assertEqual(client.events, [])

    def test_inspection_authentication_or_transport_failure_stops_sequence(self):
        for failure in (PermissionError("raw-provider-marker"), TimeoutError("raw-provider-marker")):
            client = FakeClient(inspect=failure)
            self.assert_sanitized(lambda: adapter.GoogleSDPRedactor(PROJECT, client=client).redact(TEXT))
            self.assertEqual([event[0] for event in client.events], ["inspect"])

    def test_malformed_inspection_stops_before_deidentification(self):
        malformed = (
            object(),
            SimpleNamespace(result=SimpleNamespace(findings=None)),
            SimpleNamespace(result=SimpleNamespace(findings=[finding(name="UNKNOWN_TYPE")])),
            SimpleNamespace(result=SimpleNamespace(findings=[finding(), finding()])),
            SimpleNamespace(result=SimpleNamespace(findings=[SimpleNamespace(
                info_type=SimpleNamespace(name="EMAIL_ADDRESS"),
                location=SimpleNamespace(codepoint_range=SimpleNamespace(start=0, end=9999)),
            )])),
        )
        for response in malformed:
            client = FakeClient(inspect=response)
            self.assert_sanitized(lambda: adapter.GoogleSDPRedactor(PROJECT, client=client).redact(TEXT))
            self.assertEqual([event[0] for event in client.events], ["inspect"])

    def test_deidentification_failure_never_returns_a_result(self):
        for failure in (PermissionError("raw-provider-marker"), ConnectionError("raw-provider-marker")):
            client = FakeClient(deidentify=failure)
            self.assert_sanitized(lambda: adapter.GoogleSDPRedactor(PROJECT, client=client).redact(TEXT))
            self.assertEqual([event[0] for event in client.events], ["inspect", "deidentify"])

    def test_malformed_or_empty_output_fails_closed(self):
        for response in (object(), SimpleNamespace(item=SimpleNamespace(value=None)),
                         SimpleNamespace(item=SimpleNamespace(value=" \n"))):
            client = FakeClient(deidentify=response)
            self.assert_sanitized(lambda: adapter.GoogleSDPRedactor(PROJECT, client=client).redact(TEXT))

    def test_confirmed_fragment_remaining_fails_closed(self):
        client = FakeClient(deidentify=SimpleNamespace(item=SimpleNamespace(value=TEXT)))
        self.assert_sanitized(lambda: adapter.GoogleSDPRedactor(PROJECT, client=client).redact(TEXT))

    def test_unexplained_transformation_without_findings_fails_closed(self):
        client = FakeClient(
            inspect=SimpleNamespace(result=SimpleNamespace(findings=[])),
            deidentify=SimpleNamespace(item=SimpleNamespace(value="changed")),
        )
        self.assert_sanitized(lambda: adapter.GoogleSDPRedactor(PROJECT, client=client).redact(TEXT))

    def test_real_client_factory_uses_adc_and_fixed_endpoint(self):
        created = []
        fake_dlp = types.ModuleType("google.cloud.dlp_v2")
        fake_dlp.DlpServiceClient = lambda **kwargs: created.append(kwargs) or FakeClient()
        fake_cloud = types.ModuleType("google.cloud")
        fake_cloud.dlp_v2 = fake_dlp
        fake_google = types.ModuleType("google")
        fake_google.cloud = fake_cloud
        with patch.dict(sys.modules, {
            "google": fake_google, "google.cloud": fake_cloud,
            "google.cloud.dlp_v2": fake_dlp,
        }):
            adapter.GoogleSDPRedactor(PROJECT)
        self.assertEqual(created, [{"client_options": {"api_endpoint": adapter.ENDPOINT}}])

    def test_missing_optional_sdk_does_not_break_core_imports(self):
        original_import = __import__

        def block_google(name, *args, **kwargs):
            if name.startswith("google"):
                raise ImportError("optional package unavailable")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=block_google):
            importlib.import_module("runtime.phase3.trusted_runtime")
            importlib.import_module("runtime.phase3.adapters")
            spec = importlib.util.spec_from_file_location(
                "runtime.phase3._google_sdp_test_load", adapter.__file__)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        with patch.object(adapter, "_create_client", side_effect=ImportError("raw-provider-marker")):
            self.assert_sanitized(lambda: adapter.GoogleSDPRedactor(PROJECT))


if __name__ == "__main__":
    unittest.main()
