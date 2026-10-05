"""Loopback HTTP/stub regressions; no live model, redactor or issuer claim."""
import contextlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

from runtime.agents.composition import (
    BoundaryBudget, DiagnosticTraceCollector, IntegratedCore, LocalScopedGateway,
    SharedSimulatedRedactor,
)
from runtime.agents.core import TraceCollector
from runtime.agents.credentials import ScopedCredential
from runtime.agents.demo import FakeGateway, make_demo
from runtime.agents.gateway_budget import RunAttemptBudget
from runtime.agents.presentation import present, sanitized_report
from runtime.agents.terminal_audit import TerminalAudit
from runtime.agents.terminal_diagnostics import BudgetAdmissionFailure, terminal_failure
from runtime.phase3.trusted_runtime import ControlFailure


@contextlib.contextmanager
def local_http_stub():
    """Exercise actual HTTP accounting; simulate the proxy and upstream."""
    records = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            records.append(request['metadata']['correlation_id'])
            envelope = FakeGateway().complete('secure-financial-chat',
                request['messages'][-1]['content'], {}).output
            body = json.dumps({'choices': [{'index': 0, 'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': json.dumps(envelope)}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with HTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield 'http://127.0.0.1:' + str(server.server_port), records
        finally:
            server.shutdown()
            thread.join(timeout=3)


class TerminalDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        os.chmod(self.directory.name, 0o700)
        self.journal = TerminalAudit(self.directory.name)

    def tearDown(self):
        self.journal.close()
        self.directory.cleanup()

    def cores(self, url, *, budget=None):
        budget = budget if budget is not None else RunAttemptBudget(lifetime=900)
        redactor = SharedSimulatedRedactor(BoundaryBudget())
        cores = {}
        for profile in ('financial', 'infrastructure'):
            base, auth = make_demo(profile)
            gateway = LocalScopedGateway(url, budget,
                ScopedCredential(profile, 'invalid-local-fixture-only', 1000, clock=lambda: 1),
                subject='same-fixture-subject', profile=profile, redactor=redactor)
            cores[profile] = IntegratedCore(profile, base.authenticator, base.resolver,
                base.authorizer, redactor, gateway, simulation=True, tools=base.tools,
                terminal_sink=self.journal), auth
        return cores

    def run_turn(self, cores, profile):
        core, auth = cores[profile]
        request = {'agent': profile, 'message': 'لماذا فشل دورة إعداد Docker؟'
                   if profile == 'infrastructure' else 'Expenses for January 2026',
                   'period': '2026-01' if profile == 'financial' else None,
                   'scenario_id': 'docker-config' if profile == 'infrastructure' else None}
        return core.run(auth, request, language='ar' if profile == 'infrastructure' else 'en')

    def test_shared_subject_limit_after_four_successful_bilingual_turns(self):
        with local_http_stub() as (url, records):
            cores = self.cores(url)
            for profile, count in [('financial', 3), ('financial', 3),
                                   ('infrastructure', 4), ('infrastructure', 4)]:
                result = self.run_turn(cores, profile)
                self.assertEqual((result['status'], result['model_requests']), ('completed', count))
            result = self.run_turn(cores, 'infrastructure')
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(result['terminal_failure'], {
                'stage': 'litellm', 'reason': 'subject_attempt_budget_exhausted'})
            self.assertEqual(result['model_attempt_accounting'], {
                'runtime_invocations': 3, 'budget_admissions': 2, 'budget_denials': 1,
                'http_attempts': 2, 'http_responses': 2, 'successful_traces': 2, 'blocked_traces': 1})
            self.assertEqual(len(records), 16)
            self.assertEqual(result['tool_executions'], 2)
            self.assertNotIn('facts', result)
            self.assertEqual([t['outcome'] for t in result['audit']['model_traces']],
                             ['success', 'success', 'blocked'])
            self.assertEqual(result['audit']['model_traces'][-1]['error_category'], 'attempt_budget')
            report = sanitized_report(result | {'presentation': present(result)})
            self.assertEqual(report['schema_version'], 2)
            self.assertEqual(report['terminal_failure'], result['terminal_failure'])
            self.assertEqual(report['presentation']['usage']['model_invocation_attempts'], 3)
            self.assertEqual(report['presentation']['usage']['simulated_model_requests'], 2)
            self.assertEqual(report['presentation']['usage']['gateway_http_attempts'], 2)
            reset = self.cores(url, budget=cores['financial'][0].gateway._budget)
            blocked = self.run_turn(reset, 'financial')
            self.assertEqual(blocked['model_attempt_accounting']['budget_denials'], 1)
            self.assertEqual(blocked['local_transport']['http_attempts'], 0)
            self.assertEqual(len(records), 16)
        self.journal.close()
        self.journal = TerminalAudit(self.directory.name)
        rows = [json.loads(row[0]) for row in self.journal._db.execute('SELECT event FROM events ORDER BY rowid')]
        self.assertEqual(rows[-2]['terminal_failure'], result['terminal_failure'])
        self.assertEqual(rows[-2]['model_attempt_accounting'], result['model_attempt_accounting'])

    def test_same_arabic_question_completes_below_budget_after_finance(self):
        with local_http_stub() as (url, records):
            cores = self.cores(url)
            self.assertEqual(self.run_turn(cores, 'financial')['status'], 'completed')
            result = self.run_turn(cores, 'infrastructure')
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(len(records), 7)
            self.assertEqual(result['model_attempt_accounting']['blocked_traces'], 0)

    def test_finite_budget_reasons_do_not_increase_limits(self):
        clock = [10]
        budget = RunAttemptBudget(total=2, per_subject=1, lifetime=1, clock=lambda: clock[0])
        budget.reserve('a')
        with self.assertRaises(BudgetAdmissionFailure) as caught:
            budget.reserve('a')
        self.assertEqual(terminal_failure(caught.exception)['reason'], 'subject_attempt_budget_exhausted')
        budget.reserve('b')
        with self.assertRaises(BudgetAdmissionFailure) as caught:
            budget.reserve('c')
        self.assertEqual(terminal_failure(caught.exception)['reason'], 'total_attempt_budget_exhausted')
        clock[0] = 11
        with self.assertRaises(BudgetAdmissionFailure) as caught:
            budget.reserve('c')
        self.assertEqual(terminal_failure(caught.exception)['reason'], 'run_deadline_exceeded')
        self.assertEqual(budget._used, 2)

    def test_credential_failure_is_distinct_and_has_no_http_attempt(self):
        with local_http_stub() as (url, records):
            cores = self.cores(url)
            cores['infrastructure'][0].gateway._credential.revoke()
            result = self.run_turn(cores, 'infrastructure')
            self.assertEqual(result['terminal_failure'], {'stage': 'litellm', 'reason': 'credential_unavailable'})
            self.assertEqual(result['model_attempt_accounting']['blocked_traces'], 1)
            self.assertEqual(result['local_transport']['http_attempts'], 0)
            self.assertEqual(records, [])

    def test_unknown_exception_text_and_unbounded_category_are_never_exported(self):
        private = 'private-input-connection-credential-marker'
        for error in (RuntimeError(private), ControlFailure('litellm', private)):
            self.assertEqual(terminal_failure(error), {'stage': 'agent', 'reason': 'required_control_failed'})
        with local_http_stub() as (url, _):
            cores = self.cores(url)
            with mock.patch.object(cores['infrastructure'][0].gateway, 'complete', side_effect=RuntimeError(private)):
                report = sanitized_report(self.run_turn(cores, 'infrastructure'))
            self.assertNotIn(private, json.dumps(report))

    def test_new_trace_contract_preserves_v1_and_rejects_arbitrary_fields(self):
        with local_http_stub() as (url, _):
            cores = self.cores(url)
            cores['infrastructure'][0].gateway._credential.revoke()
            row = self.run_turn(cores, 'infrastructure')['audit']['model_traces'][0]
        with self.assertRaises(ControlFailure):
            TraceCollector().emit(dict(row, schema_version=1))
        collector = DiagnosticTraceCollector()
        collector.emit(dict(row, schema_version=1))
        self.assertEqual(collector.events[0]['schema_version'], 2)
        for change in ({'error_category': 'private text'}, {'exception': 'private text'}, {'schema_version': 2}):
            with self.assertRaises(ControlFailure):
                DiagnosticTraceCollector().emit(dict(row, schema_version=1) | change)

    def test_terminal_commit_failure_blocks_delivery_even_after_tools(self):
        with local_http_stub() as (url, records):
            cores = self.cores(url)
            with mock.patch.object(self.journal, 'append', side_effect=OSError('private driver error')):
                with self.assertRaisesRegex(ControlFailure, 'audit:invalid_event'):
                    self.run_turn(cores, 'infrastructure')
            self.assertEqual(len(records), 4)
            self.assertEqual(self.journal._db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)

    def test_mixed_terminal_history_is_preserved_and_invalid_v3_is_rejected(self):
        old = {'schema_version': 2, 'event_id': 'historic-terminal-01', 'event_type': 'turn_terminal',
               'occurred_at': '2026-10-05T20:57:43+00:00', 'agent': 'infrastructure',
               'tenant_ref': '1' * 16, 'outcome': 'blocked', 'model_attempts': 3,
               'tool_attempts': 2, 'redaction_provider': 'simulated', 'model_provider': 'stub'}
        self.journal.append(old)
        historical_bytes = self.journal._db.execute('SELECT event FROM events').fetchone()[0]
        counts = {'runtime_invocations': 3, 'budget_admissions': 2, 'budget_denials': 1,
                  'http_attempts': 2, 'http_responses': 2, 'successful_traces': 2, 'blocked_traces': 1}
        new = old | {'schema_version': 3, 'event_id': 'new-terminal-01',
                     'terminal_failure': {'stage': 'litellm', 'reason': 'subject_attempt_budget_exhausted'},
                     'model_attempt_accounting': counts}
        self.journal.append(new)
        for change in ({'terminal_failure': {'stage': 'litellm', 'reason': 'raw error'}},
                       {'model_attempt_accounting': counts | {'http_attempts': 3}},
                       {'model_attempt_accounting': counts | {'budget_denials': True}},
                       {'outcome': 'completed'}, {'raw_error': 'private'}):
            with self.assertRaises(ControlFailure):
                self.journal.append(new | {'event_id': 'invalid-terminal-01'} | change)
        self.journal.close()
        self.journal = TerminalAudit(self.directory.name)
        self.assertEqual(self.journal._db.execute('SELECT event FROM events WHERE id=?',
                         ('historic-terminal-01',)).fetchone()[0], historical_bytes)
        self.assertEqual(self.journal._db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 2)
