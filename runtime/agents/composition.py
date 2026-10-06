"""Runnable local composition. Real proxy/DB; simulated model and redaction.

There is deliberately no live constructor or request-selectable endpoint/key.
The existing free-text offline UI remains a separate entry point.
"""

from datetime import datetime, timezone
import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from jsonschema import Draft202012Validator

from runtime.agents.audit_preparation import DurableToolAudit
from runtime.agents.core import AgentCore, TraceCollector
from runtime.agents.credentials import ScopedCredential
from runtime.agents.demo import SyntheticAnalyzer, SyntheticAnonymizer
from runtime.agents.gateway_budget import RunAttemptBudget, ScopedHTTPGateway
from runtime.agents.identity import SubjectGrant, TrustedJWTIdentity
from runtime.agents.protocol_preparation import canonical_decision, completion_content
from runtime.agents.tools import DemoTools
from runtime.agents.terminal_diagnostics import validate_terminal_failure
from runtime.phase3.adapters import HttpLiteLLMGateway, PresidioRedactor, _post_json
from runtime.phase3.trusted_runtime import (
    APPROVED_MODEL_ALIAS, ControlFailure, GatewayResult, redact_checked,
)


class BoundaryBudget:
    """Shared across turns, profiles and resets; failures consume reservations."""

    def __init__(self, *, operations=128, byte_limit=524288, lifetime=900,
                 clock=time.monotonic):
        if (type(operations) is not int or not 1 <= operations <= 128
                or type(byte_limit) is not int or not 1 <= byte_limit <= 524288
                or type(lifetime) not in (int, float) or not 0 < lifetime <= 900):
            raise ValueError("composition:invalid_budget")
        self.operations, self.bytes = 0, 0
        self._max_operations, self._max_bytes = operations, byte_limit
        self._clock, self._expires = clock, clock() + lifetime
        self._lock = threading.Lock()

    def reserve(self, value):
        try:
            size = len(value.encode("utf-8")) if type(value) is str else 4097
        except UnicodeError:
            size = 4097
        with self._lock:
            if (not 0 < size <= 4096 or self._clock() >= self._expires
                    or self.operations >= self._max_operations
                    or self.bytes + size > self._max_bytes):
                raise ControlFailure("redaction", "attempt_budget")
            self.operations += 1
            self.bytes += size

    def accept_output(self, value):
        try:
            size = len(value.encode("utf-8")) if type(value) is str else 4097
        except UnicodeError:
            size = 4097
        with self._lock:
            if (not 0 < size <= 4096 or self._clock() >= self._expires
                    or self.bytes + size > self._max_bytes):
                raise ControlFailure("redaction", "attempt_budget")
            self.bytes += size


class SharedSimulatedRedactor:
    """Provider-neutral seam, explicitly simulated; never qualifies live text."""

    offline_simulation = True

    def __init__(self, budget):
        self.budget = budget
        # AgentCore's existing simulation admission also sees these markers.
        self.analyzer, self.anonymizer = SyntheticAnalyzer(), SyntheticAnonymizer()
        self._delegate = PresidioRedactor(self.analyzer, self.anonymizer)

    def redact(self, value):
        self.budget.reserve(value)
        started = time.monotonic()
        result = self._delegate.redact(value)
        if time.monotonic() - started >= 8 or len(result.text.encode()) > 4096:
            raise ControlFailure("redaction", "timeout")
        self.budget.accept_output(result.text)
        return result


class ProtocolHTTPGateway(HttpLiteLLMGateway):
    """Real HTTP to the local LiteLLM server; upstream is a fixed fixture stub."""

    offline_simulation = True

    def __init__(self, base_url, *, key, redactor, transport=None):
        super().__init__(base_url, timeout=8, client_key=key)
        self._redactor = redactor
        self._post = transport or _post_json

    def complete(self, model_alias, redacted_text, metadata):
        if model_alias != APPROVED_MODEL_ALIAS or len(redacted_text.encode()) > 4000:
            raise ControlFailure("litellm", "invalid_configuration")
        self.call_count += 1
        response = self._post(self._url, {
            "model": model_alias,
            "messages": [
                {"role": "system", "content": "Return only the canonical JSON envelope: summary is the JSON decision string; classification is informational or action_required. Follow the provided tool schemas."},
                {"role": "user", "content": redacted_text},
            ],
            "response_format": {"type": "json_object"}, "max_tokens": 1024,
            "stream": False, "temperature": 0,
            "metadata": {k: metadata.get(k) for k in ("correlation_id", "tenant_ref")},
        }, self._timeout, headers={"Authorization": self._authorization})
        self.http_responses += 1
        usage = response.get('usage') if type(response) is dict else None
        if (type(usage) is dict
                and all(type(usage.get(k)) is int and 0 <= usage[k] <= 2_000_000 for k in self.usage_totals)
                and usage['prompt_tokens'] + usage['completion_tokens'] == usage['total_tokens']):
            for key in self.usage_totals:
                self.usage_totals[key] += usage[key]
        else:
            self.usage_unavailable += 1
        # Reject truncation/native tool calls before interpreting a decision.
        content = completion_content(response)
        safe = redact_checked(self._redactor, content).text
        canonical_decision(safe)
        return GatewayResult(json.loads(safe), False, "offline_simulation")


class LocalScopedGateway(ScopedHTTPGateway):
    offline_simulation = True

    def __init__(self, base_url, budget, credential, *, subject, profile, redactor, transport=None):
        super().__init__(base_url, budget, credential, subject=subject, profile=profile,
                         timeout=8)
        self._gateway = ProtocolHTTPGateway(base_url, key=self._bound_key, redactor=redactor, transport=transport)


class TenantDatabaseTools(DemoTools):
    """Real PostgreSQL leased reads with FORCE RLS; server chooses the tenant.

    Infrastructure fixtures remain fixed. Finance reads use a nonowner role,
    READ ONLY transaction, transaction-local UUID and explicit tenant predicate.
    Every path closes the lease after rollback, including rollback failure.
    """

    def __init__(self, connect, identity, directory, authorization):
        self._connect, self._identity, self._directory = connect, identity, directory
        self._authorization = authorization

    def execute(self, invocation):
        if invocation.tool.id not in {"expense_summary", "expense_categories"}:
            return super().execute(invocation)
        # Governance already authenticated the proposal. Recheck the same claims
        # against current server grants/revocation before acquiring a DB lease.
        claims = self._identity.authenticate(self._authorization)
        tenant = self._identity.resolve(claims)
        if (hashlib.sha256(claims.subject.encode()).hexdigest()[:16] != invocation.subject_ref
                or tenant != invocation.tenant or not self._identity.authorize(
                claims, tenant, invocation.tool.authorization.required_action)):
            raise ControlFailure("authorization", "denied")
        try:
            tenant_uuid = str(uuid.UUID(self._directory[tenant.tenant_id]))
        except Exception:
            raise ControlFailure("authorization", "denied") from None
        connection = None
        try:
            connection = self._connect()
            with connection.cursor() as cursor:
                cursor.execute("BEGIN READ ONLY")
                cursor.execute("SELECT pg_catalog.set_config('portfolio_demo.tenant_id', %s, true)",
                               (tenant_uuid,))
                cursor.execute("SELECT category,amount_minor_units FROM portfolio_demo.expenses "
                               "WHERE tenant_id=%s::uuid AND period=%s ORDER BY id LIMIT 21",
                               (tenant_uuid, invocation.arguments["period"]))
                rows = cursor.fetchall()
                if len(rows) > 20 or any(type(n) is not int or not 0 < n < 100000000
                                        or c not in {"office", "software", "transport"}
                                        for c, n in rows):
                    raise ValueError
                common = {"source_id": "synthetic-expenses-v1", "synthetic": True,
                          "period": invocation.arguments["period"], "currency": "SAR",
                          "data_available": bool(rows)}
                if invocation.tool.id == "expense_summary":
                    result = common | {"total_minor_units": sum(n for _, n in rows),
                                       "expense_count": len(rows)}
                else:
                    groups = [{"category": c, "total_minor_units": sum(n for x, n in rows if x == c),
                               "expense_count": sum(x == c for x, _ in rows)}
                              for c in sorted({c for c, _ in rows})]
                    groups.sort(key=lambda g: (-g["total_minor_units"], g["category"]))
                    result = common | {"categories": groups}
            connection.rollback()
            return result
        except Exception:
            raise ControlFailure("authorization", "denied") from None
        finally:
            if connection is not None:
                try:
                    connection.rollback()
                except Exception:
                    connection.close()
                    raise ControlFailure("authorization", "denied") from None
                connection.close()


class DiagnosticTraceCollector(TraceCollector):
    """Local v2 adds finite client-admission categories; historic v1 is untouched."""
    def __init__(self):
        super().__init__()
        path = Path(__file__).resolve().parents[2] / 'contracts/agents/model-trace-v2.schema.json'
        self.validator = Draft202012Validator(json.loads(path.read_text()))

    def emit(self, value):
        if value.get('schema_version') != 1:
            self.invalid = True
            raise ControlFailure('audit', 'invalid_event')
        super().emit(dict(value, schema_version=2))


class CandidateTraceCollector(TraceCollector):
    def __init__(self):
        super().__init__()
        self.validator=Draft202012Validator(json.loads((Path(__file__).resolve().parents[2]/'contracts/agents/model-trace-v3.schema.json').read_text()))
    def emit(self,value):
        if value.get('schema_version')!=1:raise ControlFailure('audit','invalid_event')
        value=dict(value,schema_version=3,redaction_provider='google_sdp_context_candidate',
                   model_provider='vertex_via_scoped_litellm',provider_receipts='unverified')
        if value['failed_stage'] in {'presidio_analyzer','presidio_anonymizer'}:value['failed_stage']='redaction'
        super().emit(value)


class IntegratedCore(AgentCore):
    """Commit bounded terminal accounting before a result can reach the UI."""

    def __init__(self, *args, terminal_sink, providers=('simulated','stub'), **kwargs):
        if providers not in {('simulated','stub'),('google_sdp_context_candidate','vertex_gemini')}:
            raise ValueError('composition:invalid_providers')
        self._providers=providers
        self._terminal = terminal_sink
        super().__init__(*args, **kwargs)

    def trace_collector(self):
        return DiagnosticTraceCollector() if self.simulation else CandidateTraceCollector()

    def run(self, *args, **kwargs):
        before = self.gateway.measurement_snapshot()
        result = super().run(*args, **kwargs)
        after = self.gateway.measurement_snapshot()
        if 'shared_run_budget' in after:result['shared_run_budget']=after['shared_run_budget']
        result["local_transport"] = {
            "http_attempts": after["http_attempts"] - before["http_attempts"],
            "http_responses": after["http_responses"] - before["http_responses"],
            "upstream": 'stub' if self.simulation else 'vertex_via_litellm',
            "external_model_calls": 0 if self.simulation else None}
        result['model_attempt_accounting'] = {
            'runtime_invocations': result['model_requests'],
            'budget_admissions': after['budget_admissions'] - before['budget_admissions'],
            'budget_denials': after['budget_denials'] - before['budget_denials'],
            'http_attempts': result['local_transport']['http_attempts'],
            'http_responses': result['local_transport']['http_responses'],
            'successful_traces': sum(t['outcome'] == 'success' for t in result['audit']['model_traces']),
            'blocked_traces': sum(t['outcome'] == 'blocked' for t in result['audit']['model_traces']),
        }
        failure = (validate_terminal_failure(result['terminal_failure'])
                   if result['status'] == 'blocked' else None)
        try:
            self._terminal.append({"schema_version": 3 if self.simulation else 4, "event_id": result["request_id"],
                "event_type": "turn_terminal", "occurred_at": datetime.now(timezone.utc).isoformat(),
                "agent": self.profile, "tenant_ref": result["tenant_ref"],
                "outcome": result["status"], "model_attempts": result["model_requests"],
                "tool_attempts": result["tool_executions"],
                "redaction_provider": self._providers[0], "model_provider": self._providers[1],
                'terminal_failure': failure,
                'model_attempt_accounting': result['model_attempt_accounting']})
        except Exception:
            # No partial answer/facts/history after an audit failure.
            raise ControlFailure("audit", "invalid_event") from None
        if not self.simulation:
            result['provider_context']={'redaction':'google_sdp_context_candidate','model':'vertex_via_scoped_litellm',
                'scope':'supervised_synthetic_trial','provider_receipts':'unverified'}
        return result


def compose_local(config, *, connect, terminal_sink, tool_sink, clock=time.time,
                  model_budget=None, redaction_budget=None):
    if config.get("mode") != "local_stub" or config.get("live_enabled") is not False:
        raise ValueError("composition:live_disabled")
    budget = model_budget if model_budget is not None else RunAttemptBudget(total=32, per_subject=16, lifetime=900)
    if not isinstance(budget, RunAttemptBudget):
        raise ValueError("composition:invalid_budget")
    redactor = SharedSimulatedRedactor(redaction_budget if redaction_budget is not None else BoundaryBudget())
    if not isinstance(redactor.budget, BoundaryBudget):
        raise ValueError("composition:invalid_budget")
    agents = {}
    for profile in ("infrastructure", "financial"):
        identity = TrustedJWTIdentity(profile, issuer="https://fixture-issuer.invalid",
            audience="portfolio-local-composition", certificates=config["certificates"],
            snapshot_expires_at=config["expires_at"],
            subjects={config["subject"]: SubjectGrant(config["tenant"],
                frozenset({"infrastructure", "financial"}))},
            tenant_reference_key=bytes.fromhex(config["tenant_reference_key"]), clock=clock)
        credential = ScopedCredential(profile, config["client_keys"][profile],
                                      config["expires_at"], clock=clock)
        gateway = LocalScopedGateway(config["gateway_url"], budget, credential,
            subject=config["subject"], profile=profile, redactor=redactor)
        tools = TenantDatabaseTools(connect, identity, config["tenant_directory"],
                                   "Bearer " + config["token"])
        core = IntegratedCore(profile, identity, identity, identity, redactor, gateway,
            simulation=True, tools=tools, audit_sink=tool_sink, terminal_sink=terminal_sink)
        agents[profile] = core, "Bearer " + config["token"]
    return agents, budget, redactor.budget
