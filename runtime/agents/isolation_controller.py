"""Trusted local broker. Rechecks governance; owns reservations and audit.

It forwards only to the single configured scoped gateway/redactor. It exposes no
shell, path, credential issuance, unrestricted HTTP or database query operation.
"""
from datetime import datetime, timezone
import hmac
import hashlib
import json
import secrets
import re
import time
import urllib.error

from runtime.agents.control_channel import check_fields
from runtime.agents.operations import OperationsBlocked
from runtime.agents.terminal_diagnostics import BudgetAdmissionFailure
from runtime.phase3.adapters import _post_json
from runtime.phase3.trusted_runtime import ControlFailure
from runtime.phase4.tool_governance import validate_and_govern_tool_invocation


class LedgerRedactor:
    def __init__(self, delegate, ledger):
        self.delegate, self.ledger, self.budget = delegate, ledger, delegate.budget
        self.analyzer, self.anonymizer = delegate.analyzer, delegate.anonymizer
        self.offline_simulation = True

    def redact(self, value):
        self.ledger.reserve('redaction_input', amount=len(value.encode()))
        result = self.delegate.redact(value)
        self.ledger.reserve('redaction_output', amount=len(result.text.encode()))
        return result


class IsolationController:
    def __init__(self, config, agents, budget, redactor, tool_audit, terminal,
                 operations, ledger):
        self.config, self.agents, self.budget, self.redactor = config, agents, budget, redactor
        self.tool_audit, self.terminal, self.operations, self.ledger = tool_audit, terminal, operations, ledger
        self.permit, self.dispatched, self.poisoned = None, set(), False
        self.safe_texts = set()
        self.http_attempts = self.http_responses = 0
        self.transport_failures = []

    def dispatch(self, operation, value):
        if operation == 'operations':
            return self.operations.handle(value)
        if operation == 'model_snapshot':
            check_fields(value, {'subject'})
            if value['subject'] != self.config['subject']:
                raise ControlFailure('authorization', 'denied')
            return self.budget.snapshot(value['subject'])
        if operation == 'model_transport_snapshot':
            check_fields(value, set())
            return {'http_attempts': self.http_attempts, 'http_responses': self.http_responses}
        if operation == 'redaction_snapshot':
            check_fields(value, set())
            return {'operations': self.redactor.budget.operations, 'bytes': self.redactor.budget.bytes}
        if operation not in {'model_reserve', 'model', 'redact', 'tool', 'audit'}:
            raise ControlFailure('authorization', 'denied')
        try:
            if self.poisoned:
                raise ControlFailure('audit', 'invalid_event')
            self.ledger._check_files()
            return self._dispatch(operation, value)
        except ControlFailure as failure:
            if failure.stage == 'audit':
                self.poisoned = self.operations.controller.poisoned = True
            raise

    def _dispatch(self, operation, value):
        if operation == 'model_reserve':
            check_fields(value, {'subject'})
            if value['subject'] != self.config['subject'] or self.permit is not None:
                raise ControlFailure('authorization', 'denied')
            self.budget.reserve(value['subject'])
            self.permit = secrets.token_hex(32)
            return self.permit
        if operation == 'model':
            if time.time() >= self.config.get('expires_at',0):
                self.permit = None
                raise ControlFailure('litellm','credential_unavailable')
            check_fields(value, {'permit', 'authorization', 'body'})
            permit, self.permit = self.permit, None
            if (type(value['permit']) is not str or permit is None
                    or not hmac.compare_digest(permit, value['permit'])
                    or value['authorization'] not in ['Bearer ' + k for k in self.config['client_keys'].values()]):
                raise ControlFailure('authorization', 'denied')
            body = value['body']
            check_fields(body, {'model', 'messages', 'response_format', 'max_tokens', 'stream', 'temperature', 'metadata'})
            if (body['model'] != 'secure-financial-chat' or body['stream'] is not False
                    or body['max_tokens'] != 1024 or body['temperature'] != 0
                    or body['response_format'] != {'type': 'json_object'}
                    or type(body['messages']) is not list or len(body['messages']) != 2
                    or [m.get('role') for m in body['messages']] != ['system', 'user']
                    or any(set(m) != {'role', 'content'} or type(m['content']) is not str
                           or len(m['content'].encode()) > 4096 for m in body['messages'])):
                raise ControlFailure('structured_input_validation', 'invalid_request')
            system = 'Return only the canonical JSON envelope: summary is the JSON decision string; classification is informational or action_required. Follow the provided tool schemas.'
            if (body['messages'][0]['content'] != system
                    or hashlib.sha256(body['messages'][1]['content'].encode()).digest() not in self.safe_texts):
                raise ControlFailure('redaction', 'incomplete_redaction')
            check_fields(body['metadata'], {'correlation_id', 'tenant_ref'})
            if (not re.fullmatch('[A-Za-z0-9._:-]{8,128}',body['metadata']['correlation_id'])
                    or not re.fullmatch('[a-f0-9]{16}',body['metadata']['tenant_ref'])):
                raise ControlFailure('structured_input_validation','invalid_request')
            self.http_attempts += 1
            try:
                result = _post_json(self.config['gateway_url'] + '/chat/completions', body, 8,
                    headers={'Authorization': value['authorization']})
            except urllib.error.HTTPError as error:
                self.transport_failures.append({'http_status': error.code})
                raise ControlFailure('litellm', 'denied' if error.code in {401,403} else 'unavailable') from None
            except Exception:
                self.transport_failures.append({'http_status': None})
                raise ControlFailure('litellm', 'unavailable') from None
            self.http_responses += 1
            return result
        if operation == 'redact':
            check_fields(value, {'text'})
            if type(value['text']) is not str or not 0 < len(value['text'].encode()) <= 4096:
                raise ControlFailure('redaction', 'invalid_request')
            result = self.redactor.redact(value['text'])
            self.safe_texts.add(hashlib.sha256(result.text.encode()).digest())
            return {'text': result.text, 'categories': list(result.categories)}
        if operation == 'audit':
            check_fields(value, {'kind', 'event'})
            if value['kind'] not in {'tool', 'terminal'}:
                raise ControlFailure('audit', 'invalid_event')
            event = value['event']
            core = self.agents['financial'][0]
            principal = core.authenticator.authenticate('Bearer ' + self.config['token'])
            tenant = core.resolver.resolve(principal)
            if type(event) is not dict or event.get('tenant_ref') not in {None, tenant.tenant_ref}:
                raise ControlFailure('audit', 'invalid_event')
            (self.tool_audit if value['kind'] == 'tool' else self.terminal).append(event)
            return {'committed': True}
        check_fields(value, {'profile', 'request_id', 'tool_id', 'arguments'})
        if value['profile'] not in self.agents:
            raise ControlFailure('authorization', 'denied')
        core, authorization = self.agents[value['profile']]
        governed = validate_and_govern_tool_invocation(core.authenticator, core.resolver,
            core.authorizer, core.assessor, core.policy, core.approval, core.registry, authorization,
            {'schema_version': 1, 'request_id': value['request_id'], 'tool_id': value['tool_id'],
             'arguments': value['arguments']}, None, now=datetime.now(timezone.utc))
        self.tool_audit._check_files()
        rows = self.tool_audit._db.execute('SELECT event FROM events WHERE id=?', (value['request_id'],)).fetchall()
        if (len(rows) != 1 or value['request_id'] in self.dispatched
                or json.loads(rows[0][0]).get('tool_id') != value['tool_id']
                or json.loads(rows[0][0]).get('tenant_ref') != governed.tenant.tenant_ref):
            raise ControlFailure('audit', 'invalid_event')
        self.dispatched.add(value['request_id'])
        from runtime.agents.trial_composition import TrialTools
        if not isinstance(core.tools, TrialTools):
            self.ledger.reserve('tool', self.config['subject'])
        return core.tools.execute(governed)
