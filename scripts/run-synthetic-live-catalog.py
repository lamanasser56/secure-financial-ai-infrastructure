#!/usr/bin/env python3
"""Prepared, once-only catalog entry point. The UI never invokes this program.

This separately hashed program is not covered by the base image's signature.
It requires a private operator admission, qualification/processor decisions and
an explicit synthetic acknowledgement before constructing any external boundary.
Current preparation provides no such admission and makes no live request.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path('/app') if '__file__' not in globals() else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.agents.audit_preparation import DurableToolAudit
from runtime.agents.composition import BoundaryBudget, ProtocolHTTPGateway, TenantDatabaseTools
from runtime.agents.conversations import ConversationStore
from runtime.agents.core import AgentCore
from runtime.agents.credentials import ScopedCredential, FORBIDDEN_APPLICATION_ENVIRONMENTS
from runtime.agents.gateway_budget import RunAttemptBudget, ScopedHTTPGateway
from runtime.agents.identity import SubjectGrant, TrustedJWTIdentity
from runtime.agents.terminal_audit import TerminalAudit
from runtime.phase3.adapters import _post_json
from runtime.phase3.trusted_runtime import ControlFailure, GatewayResult, RedactionResult, SUPPORTED_ENTITIES

CATALOG_HASH = 'acc96ad5016b93345a98edf67c3cf960f92e79d0bf211f1081e59cf2dfa3523b'
ACK = 'I_ACKNOWLEDGE_ONE_FIXED_SYNTHETIC_CATALOG_NO_AGENT_PROMOTION'
SUBJECTS = {'local-fixture-alpha', 'local-fixture-beta'}
GATEWAY = 'http://gateway.google-agent-demo.svc.cluster.local:4000'
REDACTOR = 'http://redactor.google-agent-demo.svc.cluster.local:4003/redact'


def private(path, maximum=32768):
    import stat
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
            or not 0 < info.st_size <= maximum):
        raise ValueError('demo:private_admission')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('demo:duplicate')
            value[key] = item
        return value
    return json.loads(path.read_bytes().decode('utf-8'), object_pairs_hook=unique)


def admit(admission, catalog):
    expected = {'schema_version', 'scope', 'approved', 'source_commit', 'catalog_sha256',
                'processor_review', 'fixture_issuer_accepted', 'redaction_qualification',
                'program_sha256', 'gateway_configuration_sha256', 'expires_at'}
    if (type(admission) is not dict or set(admission) != expected
            or admission['schema_version'] != 1 or admission['approved'] is not True
            or admission['scope'] != 'server_controlled_synthetic_two_agent_demo'
            or admission['processor_review'] is not True
            or admission['fixture_issuer_accepted'] is not True
            or admission['catalog_sha256'] != CATALOG_HASH
            or hashlib.sha256(catalog).hexdigest() != CATALOG_HASH
            or any(not isinstance(admission[key], str)
                   or not re.fullmatch(r'[0-9a-f]{'+str(size)+'}', admission[key])
                   for key, size in (('source_commit', 40), ('program_sha256', 64),
                                     ('gateway_configuration_sha256', 64)))
            or type(admission['expires_at']) not in (int, float)
            or not time.time() < admission['expires_at'] <= time.time() + 900):
        raise ValueError('demo:admission_rejected')
    qualification = admission['redaction_qualification']
    if (type(qualification) is not dict or set(qualification) != {'status', 'policy_sha256', 'evidence_sha256'}
            or qualification['status'] != 'QUALIFIED_FOR_THIS_SYNTHETIC_CATALOG'
            or qualification['policy_sha256'] != 'c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db'
            or not isinstance(qualification['evidence_sha256'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', qualification['evidence_sha256'])):
        raise ValueError('demo:redaction_not_qualified')
    if (os.environ.get('PORTFOLIO_SYNTHETIC_LIVE_DEMO_ACK') != ACK
            or FORBIDDEN_APPLICATION_ENVIRONMENTS & os.environ.keys()):
        raise ValueError('demo:live_disabled')


class Reservations(DurableToolAudit):
    """Committed closed counters, never text/arguments/credentials or replay."""
    @staticmethod
    def _encode(event):
        keys = {'event_id', 'kind', 'subject_ref', 'amount'}
        if (type(event) is not dict or set(event) != keys
                or not re.fullmatch(r'[0-9a-f-]{36}', event['event_id'])
                or event['kind'] not in {'model', 'tool', 'redaction_input', 'redaction_output'}
                or event['subject_ref'] not in SUBJECTS | {'shared'}
                or type(event['amount']) is not int or not 1 <= event['amount'] <= 4096):
            raise ControlFailure('audit', 'invalid_event')
        if event['kind'] in {'model', 'tool'} and event['amount'] != 1:
            raise ControlFailure('audit', 'invalid_event')
        return json.dumps(event, sort_keys=True, separators=(',', ':'))

    def totals(self):
        with self._lock:
            self._check_files()
            rows = self._db.execute('SELECT event FROM events ORDER BY rowid').fetchall()
        totals = {k: 0 for k in ('model', 'tool', 'redaction_input', 'redaction_output', 'bytes')}
        subjects = {s: 0 for s in SUBJECTS}
        for encoded, in rows:
            event = json.loads(encoded)
            if self._encode(event) != encoded:
                raise ControlFailure('audit', 'invalid_event')
            totals[event['kind']] += 1
            if event['kind'].startswith('redaction_'):
                totals['bytes'] += event['amount']
            if event['kind'] == 'model':
                subjects[event['subject_ref']] += 1
        return totals, subjects

    def reserve(self, kind, subject='shared', amount=1):
        # One admitted process owns this ledger; concurrent calls are serialized
        # by the composition and closed operator Job, never a browser endpoint.
        counts, subjects = self.totals()
        if (time.time() >= self.expires
                or (kind == 'model' and (counts['model'] >= 16 or subjects.get(subject, 8) >= 8))
                or (kind == 'tool' and counts['tool'] >= 12)
                or (kind == 'redaction_input' and counts['redaction_input'] >= 87)
                or (kind.startswith('redaction_') and counts['bytes'] + amount > 524288)):
            raise ControlFailure('audit', 'invalid_event')
        self.append({'event_id': str(uuid.uuid4()), 'kind': kind,
                     'subject_ref': subject, 'amount': amount})


class ModelBudget(RunAttemptBudget):
    def __init__(self, journal):
        super().__init__(total=16, per_subject=8, lifetime=900)
        self.journal = journal
    def reserve(self, subject):
        self.journal.reserve('model', subject)
        super().reserve(subject)


class NeutralHTTPRedactor:
    offline_simulation = False
    def __init__(self, key, journal):
        if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key):
            raise ValueError('demo:redactor_auth')
        self.key, self.journal = key, journal
        self.budget = BoundaryBudget(operations=87)
    def redact(self, value):
        self.budget.reserve(value)
        self.journal.reserve('redaction_input', amount=len(value.encode('utf-8')))
        started = time.monotonic()
        try:
            response = _post_json(REDACTOR, {'text': value}, 8,
                                  headers={'Authorization': 'Bearer ' + self.key})
            if (type(response) is not dict or set(response) != {'text', 'categories'}
                    or type(response['text']) is not str
                    or type(response['categories']) is not list
                    or len(response['categories']) != len(set(response['categories']))
                    or not set(response['categories']) <= set(SUPPORTED_ENTITIES)
                    or time.monotonic() - started >= 8):
                raise ValueError
            self.budget.accept_output(response['text'])
            self.journal.reserve('redaction_output', amount=len(response['text'].encode('utf-8')))
            return RedactionResult(response['text'], tuple(response['categories']))
        except Exception:
            raise ControlFailure('presidio_anonymizer', 'unavailable') from None


class CandidateProtocolGateway(ProtocolHTTPGateway):
    offline_simulation = False
    def complete(self, *args):
        result = super().complete(*args)
        # The inherited method performs complete-envelope/tool-protocol,
        # provider-neutral output redaction and canonical decision validation.
        return GatewayResult(result.output, True, 'live')


class CandidateScopedGateway(ScopedHTTPGateway):
    offline_simulation = False
    def __init__(self, budget, credential, *, subject, profile, redactor):
        super().__init__(GATEWAY, budget, credential, subject=subject, profile=profile, timeout=8)
        self._gateway = CandidateProtocolGateway(GATEWAY, key=self._bound_key, redactor=redactor)
        self._gateway.offline_simulation = False


class CandidateTerminal(TerminalAudit):
    @staticmethod
    def _encode(event):
        if (type(event) is not dict or event.get('schema_version') != 3
                or event.get('redaction_provider') != 'google_sdp_context_candidate'
                or event.get('model_provider') != 'vertex_gemini'):
            raise ControlFailure('audit', 'invalid_event')
        reference = dict(event, schema_version=2, redaction_provider='simulated', model_provider='stub')
        TerminalAudit._encode(reference)  # Reuse every closed field/type/date/count guard.
        return json.dumps(event, sort_keys=True, separators=(',', ':'))


class CandidateTools(TenantDatabaseTools):
    def __init__(self, *args, journal, subject):
        super().__init__(*args)
        self.journal, self.subject = journal, subject
    def execute(self, invocation):
        self.journal.reserve('tool', self.subject)
        return super().execute(invocation)


class CandidateCore(AgentCore):
    def __init__(self, *args, terminal, **kwargs):
        super().__init__(*args, **kwargs)
        self.terminal = terminal
    def run(self, *args, **kwargs):
        from datetime import datetime, timezone
        result = super().run(*args, **kwargs)
        self.terminal.append({'schema_version': 3, 'event_id': result['request_id'],
            'event_type': 'turn_terminal', 'occurred_at': datetime.now(timezone.utc).isoformat(),
            'agent': self.profile, 'tenant_ref': result['tenant_ref'], 'outcome': result['status'],
            'model_attempts': result['model_requests'], 'tool_attempts': result['tool_executions'],
            'redaction_provider': 'google_sdp_context_candidate', 'model_provider': 'vertex_gemini'})
        # Do not relabel or export historical v1 internal stage records as neutral
        # provider evidence. Only this explicit v3 summary is delivered by the Job.
        return result


def accept_catalog_result(entry, result):
    """Frozen demo acceptance, separate from runtime financial calculation.

    Completion without required governed facts is not demo success. Expected
    synthetic tenant totals are evaluation assertions, never business logic.
    """
    if result.get('status') != 'completed' or type(result.get('facts')) is not list:
        raise ValueError('demo:terminal_failure')
    facts = result['facts']
    if any(type(f) is not dict or type(f.get('tool_id')) is not str for f in facts):
        raise ValueError('demo:missing_governed_facts')
    by_tool = {f['tool_id']: f.get('result') for f in facts}
    required = ({'expense_summary', 'expense_categories'} if entry['agent'] == 'financial'
                else {'read_ci_summary', 'read_image_summary', 'read_runbook_section'})
    if len(by_tool) != len(facts) or not required <= by_tool.keys():
        raise ValueError('demo:missing_governed_facts')
    if entry['agent'] == 'financial':
        summary = by_tool['expense_summary']
        expected = {'alpha': 24000, 'beta': 9000}[entry['user']]
        if (type(summary) is not dict or type(summary.get('total_minor_units')) is not int
                or summary['total_minor_units'] != expected):
            raise ValueError('demo:synthetic_tenant_total_mismatch')


def compose(config, redactor, budget, journal, tool_sink, terminal_sink, connect):
    user = config.get('subject')
    if (user not in SUBJECTS or config.get('mode') != 'bounded_live_synthetic'
            or config.get('gateway_url') != GATEWAY
            or config.get('tenant_directory') != {
                'fixture-a': '11111111-1111-4111-8111-111111111111',
                'fixture-b': '22222222-2222-4222-8222-222222222222'}
            or config.get('tenant') != ('fixture-a' if user.endswith('alpha') else 'fixture-b')
            or not config.get('expires_at', 0) > time.time()):
        raise ValueError('demo:identity_configuration')
    agents = {}
    for profile in ('infrastructure', 'financial'):
        identity = TrustedJWTIdentity(profile, issuer='https://fixture-issuer.invalid',
            audience='portfolio-local-composition', certificates=config['certificates'],
            snapshot_expires_at=config['expires_at'],
            subjects={user: SubjectGrant(config['tenant'], frozenset({'infrastructure', 'financial'}))},
            tenant_reference_key=bytes.fromhex(config['tenant_reference_key']))
        credential = ScopedCredential(profile, config['client_keys'][profile], config['expires_at'])
        gateway = CandidateScopedGateway(budget, credential, subject=user, profile=profile, redactor=redactor)
        tools = CandidateTools(connect, identity, config['tenant_directory'], 'Bearer ' + config['token'],
                               journal=journal, subject=user)
        agents[profile] = CandidateCore(profile, identity, identity, identity, redactor, gateway,
            simulation=False, tools=tools, audit_sink=tool_sink, terminal=terminal_sink), 'Bearer ' + config['token']
    return agents


def run(admission_dir=Path('/admission'), state=Path('/state')):
    admission = private(admission_dir / 'run.json')
    raw = (admission_dir / 'synthetic-demo.json').read_bytes()
    if len(raw) > 4096:
        raise ValueError('demo:catalog_size')
    admit(admission, raw)
    code = (Path(__file__).read_bytes() if '__file__' in globals()
            else Path('/proc/self/cmdline').read_bytes().split(b'\x00')[2])
    if hashlib.sha256(code).hexdigest() != admission['program_sha256']:
        raise ValueError('demo:program_subject')
    configuration = (admission_dir / 'litellm-vertex.yaml').read_bytes()
    if hashlib.sha256(configuration).hexdigest() != admission['gateway_configuration_sha256']:
        raise ValueError('demo:gateway_configuration')
    # Admission commits before constructing any transport, connection or SDK.
    fd = os.open(state / 'started.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump({'catalog_sha256': CATALOG_HASH, 'source_commit': admission['source_commit'],
                   'program_sha256': admission['program_sha256'], 'authority_changed': False}, out)
        out.flush(); os.fsync(out.fileno())
    directory = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(directory)
    finally: os.close(directory)
    import psycopg
    for name in ('reservations', 'tools', 'terminals'):
        (state / name).mkdir(mode=0o700)
    journal, tools, terminals = Reservations(state / 'reservations'), DurableToolAudit(state / 'tools'), CandidateTerminal(state / 'terminals')
    journal.expires = admission['expires_at']
    redactor_config = private(admission_dir / 'redactor-client.json')
    if set(redactor_config) != {'key'}:
        raise ValueError('demo:redactor_configuration')
    redactor, budget = NeutralHTTPRedactor(redactor_config['key'], journal), ModelBudget(journal)
    stores, rows = {}, []
    try:
        for user in ('alpha', 'beta'):
            config = private(admission_dir / ('application-' + user + '.json'))
            if not config['subject'].endswith('-' + user):
                raise ValueError('demo:identity_configuration')
            agents = compose(config, redactor, budget, journal, tools, terminals,
                             lambda c=config: psycopg.connect(c['tenant_database_url'], connect_timeout=2))
            store = ConversationStore(agents)
            stores[user] = store, store.bootstrap()[0]
        for entry in json.loads(raw)['inputs']:
            if time.time() >= journal.expires:
                raise ValueError('demo:deadline')
            store, session = stores[entry['user']]
            frame = store.turn(session, {k: entry[k] for k in ('agent', 'language', 'question', 'evidence_source')} | {'conversation_id': None})
            result = frame['response']
            rows.append({'id': entry['id'], 'status': result['status'],
                         'model_attempts': result['model_requests'], 'tools': result['tool_executions']})
            accept_catalog_result(entry, result)
        totals, _ = journal.totals()
        receipt = {'schema_version': 3, 'scope': admission['scope'], 'cases': rows,
                   'reserved': totals, 'upstream': 'vertex_gemini', 'redaction': 'google_sdp_context_candidate',
                   'provider_receipts': None, 'billed_usage': None, 'retries': 0,
                   'authority_changed': False, 'promotion_authorized': False}
        (state / 'result.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print(json.dumps(receipt))
        return receipt
    finally:
        for sink in (journal, tools, terminals):
            sink.close()


if __name__ == '__main__':
    os.umask(0o077)
    if len(sys.argv) != 1:
        raise SystemExit('demo:arguments_rejected')
    try:
        run()
    except Exception:
        print(json.dumps({'status': 'BLOCKED', 'code': 'SYNTHETIC_DEMO_GATE_OR_EXECUTION_FAILURE',
                          'automatic_retry': False, 'promotion_authorized': False}))
        raise SystemExit(1) from None
