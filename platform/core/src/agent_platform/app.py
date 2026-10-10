"""Front door (apps namespace): the existing bilingual UI + Financial Agent, live in-cluster, plus the
Security & Operations dashboard backed by the ops agent.

Reuses the qualified agent core unchanged (IntegratedCore, TenantDatabaseTools, DeterministicEmailRedactor,
DemoServer): only the transport changes, from laptop tunnels to cluster Services. The UI listens on loopback;
access is `kubectl port-forward deploy/app 8080:8080`. Identity is server-selected (a synthetic fixture issuer
whose key lives only in this Pod's Secret); tokens, scoped credentials and the per-hour run budget are
re-issued every 50 minutes. The durable cost ceiling is the gateway key budget ($10/month).
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
import uuid

from agent_platform import audit
from agent_platform.identity_fixture import mint
from agent_platform.ops.approval import Signer
from agent_platform.redaction import RedactorClient

GATEWAY = 'http://gateway.platform.svc.cluster.local:4000'
REDACTOR = 'http://redactor.platform.svc.cluster.local:4003'
OPS = 'http://ops-agent.ops.svc.cluster.local:8090'
SESSION_SECONDS, REFRESH_SECONDS = 3600, 3000
PROFILES = ('financial', 'infrastructure')
ACTIONS = ('restart', 'rollback', 'scale')


def load_config(path=Path('/secrets/app/app.json')):
    config = json.loads(path.read_text())
    required = {'issuer_private_key', 'issuer_certificate', 'tenant_reference_key', 'tenant_directory', 'tenant_database_url',
                'client_keys', 'redactor_key', 'approver_private_key', 'operator_secret_scrypt', 'ops_api_key', 'users'}
    if set(config) != required or set(config['client_keys']) != set(PROFILES):
        raise SystemExit('app:config_rejected')
    return config


def compose(config, user, connect):
    """One hour-long session: identity snapshot, token, scoped credentials and run budget."""
    from runtime.agents.composition import IntegratedCore, TenantDatabaseTools, BoundaryBudget
    from runtime.agents.credentials import ScopedCredential
    from runtime.agents.gateway_budget import RunAttemptBudget, ScopedHTTPGateway
    from runtime.agents.identity import SubjectGrant, TrustedJWTIdentity
    from runtime.agents.composition import ProtocolHTTPGateway
    from runtime.phase3.deterministic_email import DeterministicEmailRedactor
    from runtime.phase3.trusted_runtime import GatewayResult

    subject, tenant = config['users'][user]['subject'], config['users'][user]['tenant']
    now = int(time.time())
    expires = now + SESSION_SECONDS
    token = mint(config['issuer_private_key'], subject=subject, tenant=tenant, issued_at=now, expires_at=expires)
    budget = RunAttemptBudget(total=32, per_subject=16, lifetime=SESSION_SECONDS)
    redactor = DeterministicEmailRedactor(RedactorClient(REDACTOR, config['redactor_key'], budget=BoundaryBudget(lifetime=900)))

    class LiveGateway(ScopedHTTPGateway):
        offline_simulation = False

        def __init__(self, budget, credential, *, subject, profile, redactor):
            super().__init__(GATEWAY, budget, credential, subject=subject, profile=profile, timeout=8)

            class Protocol(ProtocolHTTPGateway):
                offline_simulation = False

                def complete(self, *args):
                    result = super().complete(*args)
                    return GatewayResult(result.output, True, 'live')
            self._gateway = Protocol(GATEWAY, key=self._bound_key, redactor=redactor)

    agents = {}
    for profile in PROFILES:
        identity = TrustedJWTIdentity(profile, issuer='https://fixture-issuer.invalid', audience='portfolio-local-composition',
                                      certificates={'platform-fixture': config['issuer_certificate']}, snapshot_expires_at=expires,
                                      subjects={subject: SubjectGrant(tenant, frozenset(PROFILES))},
                                      tenant_reference_key=bytes.fromhex(config['tenant_reference_key']))
        credential = ScopedCredential(profile, config['client_keys'][profile], expires)
        gateway = LiveGateway(budget, credential, subject=subject, profile=profile, redactor=redactor)
        tools = TenantDatabaseTools(connect, identity, config['tenant_directory'], 'Bearer ' + token)
        core = IntegratedCore(profile, identity, identity, identity, redactor, gateway, simulation=False, tools=tools,
                              audit_sink=AuditSink('tool'), terminal_sink=AuditSink('turn'),
                              providers=('google_sdp_context_candidate', 'vertex_gemini'))
        agents[profile] = core, 'Bearer ' + token
    return agents, expires


class AuditSink:
    """Agent-core audit sink -> structured audit lines (bounded metadata only, never content)."""
    SAFE = ('event_id', 'event_type', 'agent', 'tenant_ref', 'outcome', 'model_attempts', 'tool_attempts', 'tool_id',
            'authorization_result', 'injection_result', 'policy_outcome', 'policy_reason_code', 'governance_result')

    def __init__(self, kind):
        self.kind = kind

    def append(self, event):
        if not isinstance(event, dict):
            import dataclasses
            event = dataclasses.asdict(event) if dataclasses.is_dataclass(event) else dict(vars(event))
        audit.emit('agent_' + self.kind, 'app', **{k: event[k] for k in self.SAFE if k in event})

    def close(self):
        pass


class ClusterOperations:
    """Implements the existing operations UI protocol against the in-cluster ops agent."""

    def __init__(self, config, *, opener=None, clock=time.time):
        self._config, self._clock = config, clock
        self._signer = Signer(config['approver_private_key'], approver='owner', clock=clock)
        self._open = opener or urllib.request.build_opener(urllib.request.ProxyHandler({})).open
        self._approvals, self._lock = {}, threading.Lock()
        self.controller = self

    def budgets(self):
        return {'expiry_epoch': int(self._clock()) + SESSION_SECONDS, 'live_enabled': True, 'monthly_budget_usd': 10,
                'approval_ttl_seconds': 300}

    def _call(self, method, path, body=None):
        request = urllib.request.Request(OPS + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                         headers={'Authorization': 'Bearer ' + self._config['ops_api_key'],
                                                  'Content-Type': 'application/json'})
        with self._open(request, timeout=200) as response:
            return json.loads(response.read(1 << 20))

    def _blocked(self, code):
        from runtime.agents.operations import OperationsBlocked
        return OperationsBlocked(code)

    def handle(self, request):
        operation = request.get('operation')
        snapshot = self._call('GET', '/v1/snapshot') if operation not in ('security', 'execute') else None
        if operation == 'overview':
            return {'targets': [{'target_id': k, 'mutable': True, 'kind': 'deployment'} for k in sorted(snapshot['findings'])],
                    'actions': list(ACTIONS), 'budgets': self.budgets(), 'recent': snapshot['timeline'][-20:],
                    'timeline': snapshot['timeline'], 'pending': snapshot['pending'], 'denials': snapshot['denials'],
                    'identity_authority': 'platform_fixture_owner', 'financial_ui': '/', 'model_boundary': 'gateway_via_redactor'}
        if operation in ('observe', 'diagnose', 'explain', 'propose'):
            finding = snapshot['findings'].get(request.get('target_id'))
            if finding is None:
                raise self._blocked('TARGET_DENIED')
            finding = dict(finding, target_id=request['target_id'], evidence_id=finding['evidence_digest'])
            if operation == 'observe':
                return finding
            if operation == 'diagnose':
                return dict(finding, permitted_action=(finding['suggested_actions'] or [None])[0])
            matches = [p for p in snapshot['pending'] if p['target'] == request['target_id']
                       and (operation == 'explain' or (p['action'] == request.get('action') and p['evidence_digest'] == request.get('evidence_id')))]
            if operation == 'explain':
                return {'evidence': finding, 'explanations': [p.get('explanation') for p in matches], 'untrusted_model_text': True}
            if not matches:
                raise self._blocked('NO_AGENT_PROPOSAL')
            return matches[-1]
        if operation == 'approve':
            secret = request.get('operator_secret', '')
            expected = self._config['operator_secret_scrypt']
            digest = hashlib.scrypt(secret.encode(), salt=bytes.fromhex(expected['salt']), n=2 ** 14, r=8, p=1).hex()
            proposal = next((p for p in snapshot['pending'] if p['request_id'] == request.get('request_id')), None)
            if not hmac.compare_digest(digest, expected['hash']) or proposal is None:
                audit.emit('ops_approval_refused', 'app', request_id=request.get('request_id'))
                raise self._blocked('APPROVAL_DENIED')
            approval_id = str(uuid.uuid4())
            token = self._signer.sign(proposal)
            with self._lock:
                self._approvals[approval_id] = (proposal['request_id'], token, self._clock() + 300)
            audit.emit('ops_approval_signed', 'app', request_id=proposal['request_id'], target=proposal['target'], action=proposal['action'])
            return {'request_id': proposal['request_id'], 'approval_id': approval_id, 'target': proposal['target'],
                    'action': proposal['action'], 'expires_in_seconds': 300}
        if operation == 'execute':
            with self._lock:
                saved = self._approvals.pop(request.get('approval_id'), None)
            if saved is None or saved[0] != request.get('request_id') or self._clock() >= saved[2]:
                raise self._blocked('APPROVAL_DENIED')
            return self._call('POST', '/v1/execute', {'request_id': saved[0], 'approval': saved[1]})
        if operation == 'security':
            return self._call('GET', '/v1/posture')
        raise self._blocked('INVALID_REQUEST')


def main():
    import psycopg
    from runtime.agents.web import DemoServer
    config = load_config()
    user = os.environ.get('PORTFOLIO_USER', 'alpha')
    if user not in config['users']:
        raise SystemExit('app:user_rejected')
    connect = lambda: psycopg.connect(config['tenant_database_url'], connect_timeout=2)
    agents, expires = compose(config, user, connect)
    shared = dict(agents)
    with DemoServer(('127.0.0.1', 8080), agents=shared, composition='platform_live',
                    operations=ClusterOperations(config)) as server:
        def refresh():
            while True:
                time.sleep(REFRESH_SECONDS)
                try:
                    fresh, _ = compose(config, user, connect)
                    shared.update(fresh)  # conversations read agents per request; ephemeral history is preserved by profile
                    audit.emit('app_session_refreshed', 'app', profiles=list(fresh))
                except Exception as error:
                    audit.emit('app_session_refresh_failed', 'app', reason=type(error).__name__)
        threading.Thread(target=refresh, daemon=True).start()
        audit.emit('app_started', 'app', user=user, session_expires=expires)
        server.serve_forever()


if __name__ == '__main__':
    main()
