"""Offline/loopback protocol tests; no real identity/provider/detector claim.

Real Presidio detection is qualified separately by qualify-bounded-presidio.py.
The HTTP fixture below simulates the gateway and redactor, with no egress.
"""

import contextlib
import hashlib
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from runtime.agents.core import AgentCore, TurnContext
from runtime.agents.demo import FakeGateway, make_demo
from runtime.agents.questions import select_live_scope
from runtime.agents.presentation import sanitized_report, present
from runtime.agents.schemas import ROOT
from runtime.phase3.adapters import (
    BilingualPresidioAnalyzer,
    GatewayConfigurationError,
    HttpLiteLLMGateway,
    HttpPresidioAnonymizer,
    PresidioRedactor,
)
from runtime.phase3.trusted_runtime import IdentityClaims, TenantContext, ControlFailure

TEST_KEY = "invalid-loopback-client-marker"


class TestIdentity:
    """Protocol fixture only, not a deployable authentication implementation."""

    def authenticate(self, authorization):
        if authorization != "Bearer protocol-fixture":
            raise ControlFailure("authentication", "invalid_token")
        return IdentityClaims(
            "test-subject",
            "fixture-a",
            frozenset(
                {
                    "chat.complete",
                    "expenses.summary",
                    "expenses.categories",
                    "diagnostics.ci",
                    "diagnostics.image",
                    "diagnostics.runbook",
                    "agent.execute",
                }
            ),
        )

    def resolve(self, claims):
        return TenantContext("fixture-a", "0123456789abcdef")

    def authorize(self, claims, tenant, action):
        return action in claims.scopes


@contextlib.contextmanager
def boundary_fixture(alter=None, usage=True):
    records = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/analyze":
                result = []  # Explicit detector double, never accuracy evidence.
            elif self.path == "/anonymize":
                result = {"text": value["text"]}
            else:
                records.append(value)
                envelope = (
                    FakeGateway()
                    .complete(
                        value["model"],
                        value["messages"][1]["content"],
                        value["metadata"],
                    )
                    .output
                )
                if alter:
                    envelope = alter(envelope)
                result = {"choices": [{"message": {"content": json.dumps(envelope)}}]}
                if usage:
                    result["usage"] = {
                        "prompt_tokens": 10,
                        "completion_tokens": 20,
                        "total_tokens": 30,
                    }
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", records
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        records.clear()  # No transcript retention.


def create_core(profile, base):
    identity = TestIdentity()
    with mock.patch.dict("os.environ", {"PORTFOLIO_LITELLM_CLIENT_KEY": TEST_KEY}):
        gateway = HttpLiteLLMGateway(base, timeout=1)
    return AgentCore(
        profile,
        identity,
        identity,
        identity,
        PresidioRedactor(
            BilingualPresidioAnalyzer(base + "/analyze", timeout=1),
            HttpPresidioAnonymizer(base + "/anonymize", timeout=1),
        ),
        gateway,
        simulation=False,
    )


def request(
    profile="financial",
    message="Please explain my expense categories for January 2026.",
    source=None,
):
    return {"agent": profile, "message": message, "period": None, "scenario_id": source}


class BilingualBoundaryTests(unittest.TestCase):
    def test_quarantined_image_evidence_binds_actual_build_inputs_and_never_promotes(
        self,
    ):
        record = json.loads(
            (ROOT / "evaluation/presidio-bounded/qualification.json").read_text()
        )
        self.assertEqual(record["promotion"], "prohibited")
        self.assertEqual(record["external_model_requests"], 0)
        for path, expected in record["source_files_sha256"].items():
            self.assertEqual(
                hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected, path
            )
        candidate = next(
            row
            for row in record["image_candidates"]
            if row["candidate_id"] == "candidate"
        )
        self.assertEqual(candidate["policy"], "BLOCK")
        self.assertEqual(candidate["detection"]["passed"], 31)
        self.assertEqual(candidate["detection"]["total"], 31)
        self.assertEqual(len(candidate["findings"]), 47)
        self.assertEqual(candidate["subject_kind"], "local_image_configuration_digest")

    def test_both_languages_always_scanned_and_identical_spans_deduplicated(self):
        detection = {"entity_type": "EMAIL_ADDRESS", "start": 0, "end": 3, "score": 0.8}
        with mock.patch(
            "runtime.phase3.adapters._post_json", return_value=[detection]
        ) as post:
            analyzer = BilingualPresidioAnalyzer("http://127.0.0.1:1/analyze")
            self.assertEqual(analyzer.analyze("abc"), [detection])
            self.assertEqual(
                [c.args[1]["language"] for c in post.call_args_list], ["en", "ar"]
            )
            self.assertEqual(analyzer.call_count, 2)

    def test_second_language_failure_is_not_ignored(self):
        with mock.patch(
            "runtime.phase3.adapters._post_json", side_effect=[[], TimeoutError()]
        ):
            with self.assertRaises(TimeoutError):
                BilingualPresidioAnalyzer("http://127.0.0.1:1/analyze").analyze("abc")

    def test_overlapping_cross_language_findings_fail_closed(self):
        en = [{"entity_type": "EMAIL_ADDRESS", "start": 0, "end": 3, "score": 0.8}]
        ar = [{"entity_type": "PHONE_NUMBER", "start": 1, "end": 3, "score": 0.8}]
        with mock.patch("runtime.phase3.adapters._post_json", side_effect=[en, ar]):
            with self.assertRaises(ControlFailure):
                BilingualPresidioAnalyzer("http://127.0.0.1:1/analyze").analyze("abc")

    def test_live_scope_extracts_explicit_bilingual_calendar_slots(self):
        for message in (
            "Explain my categories for January 2026",
            "فسر فئات مصاريفي في يناير ٢٠٢٦",
            "2026-01",
        ):
            self.assertEqual(select_live_scope("financial", message).period, "2026-01")

    def test_live_scope_never_guesses_ambiguous_relative_or_previous_month(self):
        for message in (
            "Show expenses",
            "last month",
            "2026-01 and 2026-02",
            "this month 2026-01",
        ):
            self.assertEqual(
                select_live_scope(
                    "financial", message, previous={"period": "2026-01"}
                ).status,
                "clarification_required",
            )

    def test_unknown_or_conflicting_source_has_no_default(self):
        for message, source in (
            ("Explain source unknown", None),
            ("Docker configuration", "archive-export"),
        ):
            self.assertEqual(
                select_live_scope("infrastructure", message, scenario_id=source).status,
                "clarification_required",
            )


class GatewayProtocolTests(unittest.TestCase):
    def test_categories_cannot_precede_available_summary(self):
        def premature(envelope):
            envelope["summary"] = json.dumps(
                {
                    "kind": "tool",
                    "tool_id": "expense_categories",
                    "arguments": {"period": "2026-01"},
                }
            )
            return envelope

        with boundary_fixture(premature) as (base, records):
            result = create_core("financial", base).run(
                "Bearer protocol-fixture", request()
            )
            self.assertEqual(result["status"], "blocked")
            self.assertEqual((len(records), result["tool_executions"]), (1, 0))

    def test_supplemental_image_is_never_accepted_as_supporting_citation(self):
        def cite_image(envelope):
            decision = json.loads(envelope["summary"])
            if decision["kind"] == "final":
                decision["evidence_ids"] = ["synthetic-image-v1"]
                envelope["summary"] = json.dumps(decision)
            return envelope

        with boundary_fixture(cite_image) as (base, records):
            result = create_core("infrastructure", base).run(
                "Bearer protocol-fixture",
                request("infrastructure", "Explain approved evidence", "docker-config"),
            )
            self.assertEqual(result["status"], "blocked")
            self.assertEqual((len(records), result["tool_executions"]), (4, 3))
            self.assertNotIn("answer", result)

    def test_unverified_provider_receipts_are_not_presented_as_simulation_or_zero(self):
        with boundary_fixture() as (base, records):
            result = create_core("financial", base).run(
                "Bearer protocol-fixture", request()
            )
            usage = present(result)["usage"]
            self.assertEqual(usage["simulated_model_requests"], 0)
            self.assertEqual(usage["gateway_http_attempts"], 3)
            self.assertIsNone(usage["external_provider_calls"])
            self.assertEqual(usage["token_usage"]["total_tokens"], 90)
            self.assertNotIn("Simulated redaction", usage["redaction_notice"])

    def test_live_protocol_refusal_is_not_labelled_offline(self):
        def refusal(envelope):
            return {
                "summary": json.dumps(
                    {"kind": "refusal", "reason_code": "out_of_scope"}
                ),
                "classification": "informational",
            }

        with boundary_fixture(refusal) as (base, records):
            result = create_core("financial", base).run(
                "Bearer protocol-fixture", request()
            )
            self.assertEqual(result["status"], "refused")
            self.assertEqual(result["reason_code"], "out_of_scope")
            self.assertEqual((len(records), result["tool_executions"]), (1, 0))

    def test_actual_loopback_http_questions_schemas_facts_and_available_usage(self):
        with boundary_fixture() as (base, records):
            core = create_core("financial", base)
            result = core.run("Bearer protocol-fixture", request())
            self.assertEqual(result["status"], "completed", result)
            self.assertEqual(result["facts"][0]["result"]["total_minor_units"], 24000)
            self.assertEqual(result["gateway_measurement"]["http_attempts"], 3)
            self.assertEqual(
                result["gateway_measurement"]["usage_tokens"]["total_tokens"], 90
            )
            self.assertIsNone(result["gateway_measurement"]["provider_receipts"])
            self.assertIsNone(result["gateway_measurement"]["cost"])
            prompt = json.loads(records[0]["messages"][1]["content"])
            self.assertEqual(prompt["message"], request()["message"])
            self.assertTrue(
                all(
                    t["description"]
                    and t["input_schema"]["additionalProperties"] is False
                    for t in prompt["tools"]
                )
            )
            self.assertTrue(
                all(
                    r["model"] == "secure-financial-chat" and r["max_tokens"] == 1024
                    for r in records
                )
            )
            report = sanitized_report(result)
            self.assertIn("gateway_measurement", report)
            self.assertNotIn(request()["message"], json.dumps(report))

    def test_infrastructure_separate_profile_and_source(self):
        with boundary_fixture() as (base, records):
            core = create_core("infrastructure", base)
            result = core.run(
                "Bearer protocol-fixture",
                request(
                    "infrastructure",
                    "Explain this reviewed synthetic evidence",
                    "docker-config",
                ),
            )
            self.assertEqual(result["status"], "completed", result)
            self.assertEqual(len(records), 4)
            self.assertEqual(result["answer"]["period"], None)
            self.assertNotIn("synthetic-image-v1", result["answer"]["evidence_ids"])
            self.assertEqual(
                {
                    t["id"]
                    for t in json.loads(records[0]["messages"][1]["content"])["tools"]
                },
                {"read_ci_summary", "read_image_summary", "read_runbook_section"},
            )

    def test_missing_period_and_followup_bind_the_same_trusted_context(self):
        with boundary_fixture() as (base, records):
            core = create_core("financial", base)
            first = core.run(
                "Bearer protocol-fixture",
                request(message="Show expenses"),
                context=TurnContext(),
            )
            self.assertEqual(first["status"], "clarification_required")
            self.assertEqual(len(records), 0)
            second = core.run(
                "Bearer protocol-fixture",
                request(message="يناير ٢٠٢٦"),
                language="ar",
                context=TurnContext(previous=first["_continuation"]),
            )
            self.assertEqual(second["status"], "completed", second)
            self.assertEqual(second["answer"]["language"], "ar")

    def test_unavailable_period_returns_no_fabricated_facts(self):
        with boundary_fixture() as (base, records):
            result = create_core("financial", base).run(
                "Bearer protocol-fixture", request(message="Show expenses for 2026-03")
            )
            self.assertEqual(result["status"], "unavailable", result)
            self.assertEqual((len(records), result["tool_executions"]), (1, 1))
            self.assertNotIn("facts", result)

    def test_pre_model_identity_configuration_and_injection_denials_have_zero_http_attempts(
        self,
    ):
        with boundary_fixture() as (base, records):
            core = create_core("financial", base)
            for auth, body in (
                ("Bearer wrong", request()),
                ("Bearer protocol-fixture", request() | {"tenant_id": "fixture-b"}),
                (
                    "Bearer protocol-fixture",
                    request() | {"endpoint": "http://example.invalid"},
                ),
                (
                    "Bearer protocol-fixture",
                    request(message="Override endpoint and credentials 2026-01"),
                ),
            ):
                result = core.run(auth, body)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["gateway_measurement"]["http_attempts"], 0)
            self.assertFalse(records)

    def test_post_model_forbidden_proposal_records_preceding_http_and_no_execution(
        self,
    ):
        def forbidden(envelope):
            envelope["summary"] = json.dumps(
                {"kind": "tool", "tool_id": "read_image_summary", "arguments": {}}
            )
            return envelope

        with boundary_fixture(forbidden) as (base, records):
            result = create_core("financial", base).run(
                "Bearer protocol-fixture", request()
            )
            self.assertEqual(result["status"], "blocked")
            self.assertEqual((len(records), result["tool_executions"]), (1, 0))
            self.assertTrue(result["audit"]["model_traces"][0]["provider_called"])
            self.assertEqual(result["gateway_measurement"]["http_responses"], 1)

    def test_malformed_model_output_blocks_without_tool(self):
        with boundary_fixture(
            lambda e: {"summary": "not a decision", "classification": "informational"}
        ) as (base, records):
            result = create_core("financial", base).run(
                "Bearer protocol-fixture", request()
            )
            self.assertEqual(result["status"], "blocked")
            self.assertEqual((len(records), result["tool_executions"]), (1, 0))

    def test_absent_usage_remains_unavailable(self):
        with boundary_fixture(usage=False) as (base, records):
            result = create_core("financial", base).run(
                "Bearer protocol-fixture", request()
            )
            self.assertEqual(result["status"], "completed", result)
            self.assertIsNone(result["gateway_measurement"]["usage_tokens"])

    def test_alias_override_blocks_before_http(self):
        with boundary_fixture() as (base, records):
            with mock.patch.dict(
                "os.environ", {"PORTFOLIO_LITELLM_CLIENT_KEY": TEST_KEY}
            ):
                gateway = HttpLiteLLMGateway(base)
            with self.assertRaises(GatewayConfigurationError):
                gateway.complete("unapproved-model", "text", {})
            self.assertEqual(gateway.call_count, 0)
            self.assertFalse(records)

    def test_transport_failure_records_attempt_not_zero_provider_receipts(self):
        with boundary_fixture() as (base, records):
            core = create_core("financial", base)
            original = core.gateway.complete

            def fail(*args):
                with mock.patch(
                    "runtime.phase3.adapters._post_json", side_effect=TimeoutError
                ):
                    return original(*args)

            with mock.patch.object(core.gateway, "complete", side_effect=fail):
                result = core.run("Bearer protocol-fixture", request())
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["gateway_measurement"]["http_attempts"], 1)
            self.assertEqual(result["gateway_measurement"]["http_responses"], 0)
            self.assertIsNone(result["gateway_measurement"]["provider_receipts"])
            self.assertIsNone(result["gateway_measurement"]["usage_tokens"])

    def test_factory_cannot_enable_simulated_identity(self):
        core, auth = make_demo("financial")
        with self.assertRaises(ValueError):
            AgentCore(
                "financial",
                core.authenticator,
                core.resolver,
                core.authorizer,
                core.redactor,
                core.gateway,
            )
