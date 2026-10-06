"""Agent application inside the qualified network-none, read-only container.

All model transport, SQL, durable audit and host actions use the peer-checked
controller channel. No administrator/database/cloud credential is in this file.
"""
import json
import os
from pathlib import Path
import socket
import socketserver
import time

from runtime.agents.composition import IntegratedCore, LocalScopedGateway
from runtime.agents.control_channel import ControlClient, RemoteAudit, RemoteOperations, peer
from runtime.agents.credentials import ScopedCredential
from runtime.agents.gateway_budget import RunAttemptBudget
from runtime.agents.identity import SubjectGrant, TrustedJWTIdentity
from runtime.agents.web import DemoServer, Handler
from runtime.phase3.trusted_runtime import ControlFailure, GatewayResult, RedactionResult


class RemoteBudget(RunAttemptBudget):
    def __init__(self, client):
        super().__init__(total=32, per_subject=16, lifetime=900)
        self.client = client

    def reserve(self, subject):
        self.client.permit = self.client.call('model_reserve', {'subject': subject})

    def snapshot(self, subject):
        return self.client.call('model_snapshot', {'subject': subject})


class RemoteBoundary:
    _max_operations, _max_bytes = 87, 524288

    def __init__(self, client):
        self.client = client

    @property
    def operations(self):
        return self.client.call('redaction_snapshot', {})['operations']

    @property
    def bytes(self):
        return self.client.call('redaction_snapshot', {})['bytes']


class ChannelRedactor:
    def __init__(self, client, *, simulation):
        self.client, self.offline_simulation = client, simulation
        self.budget = RemoteBoundary(client)
        if simulation:
            self.analyzer = self.anonymizer = type('SimulatedBoundary', (), {'offline_simulation': True})()

    def redact(self, text):
        value = self.client.call('redact', {'text': text})
        if type(value) is not dict or set(value) != {'text', 'categories'}:
            raise ControlFailure('redaction', 'malformed_result')
        return RedactionResult(value['text'], tuple(value['categories']))


class ChannelTools:
    def __init__(self, client, profile):
        self.client, self.profile = client, profile

    def execute(self, invocation):
        return self.client.call('tool', {'profile': self.profile,
            'request_id': invocation.request_id, 'tool_id': invocation.tool.id,
            'arguments': invocation.arguments})


class ChannelGateway(LocalScopedGateway):
    def __init__(self, *args, simulation, **kwargs):
        self.channel = kwargs['transport'].__self__
        super().__init__(*args, **kwargs)
        self.offline_simulation = simulation
        if not simulation:
            old = self._gateway
            class Candidate(type(old)):
                offline_simulation = False
                def complete(self, *values):
                    result = super().complete(*values)
                    return GatewayResult(result.output, True, 'live')
            old.__class__ = Candidate

    def measurement_snapshot(self):
        return super().measurement_snapshot() | self.channel.call('model_transport_snapshot', {})


class FixedConversations:
    """The separately admitted fixed qualification cannot open own-wording chat."""
    questions = (('en','Explain my spending for 2026-01 and rank its categories.'),
                 ('ar','اشرح مصاريفي في 2026-01 ورتب التصنيفات حسب المبلغ'))
    def __init__(self, delegate):
        self.delegate, self.used = delegate, 0
    def __getattr__(self,name):
        return getattr(self.delegate,name)
    def turn(self, token, request):
        from runtime.agents.conversations import ConversationRejected
        if (self.used >= len(self.questions) or request.get('agent') != 'financial'
                or (request.get('language'),request.get('question')) != self.questions[self.used]):
            raise ConversationRejected('fixed_qualification_input_rejected')
        self.used += 1  # Failed dispatch consumes the fixed input; never replay.
        return self.delegate.turn(token,request)
    def reset(self,*args):
        from runtime.agents.conversations import ConversationRejected
        raise ConversationRejected('fixed_qualification_reset_denied')


class FinancialConversations:
    """The legacy infrastructure chat has no current live qualification."""
    def __init__(self, delegate):
        self.delegate = delegate
    def __getattr__(self, name):
        return getattr(self.delegate, name)
    def turn(self, token, request):
        from runtime.agents.conversations import ConversationRejected
        if request.get('agent') != 'financial':
            raise ConversationRejected('profile_not_admitted')
        return self.delegate.turn(token, request)
    def reset(self, token, request):
        from runtime.agents.conversations import ConversationRejected
        if request.get('agent') != 'financial':
            raise ConversationRejected('profile_not_admitted')
        return self.delegate.reset(token, request)


class UnixDemoServer(DemoServer):
    address_family = socket.AF_UNIX

    def __init__(self, path, port, agents, operations, composition, owner_uid, scope):
        from runtime.agents.conversations import ConversationStore
        self.agents, self.operations, self.composition = agents, operations, composition
        self.conversations = ConversationStore(agents)
        if scope == 'fixed_inputs_qualification':
            self.conversations = FixedConversations(self.conversations)
        elif composition == 'supervised_candidate_live':
            self.conversations = FinancialConversations(self.conversations)
        self.owner_uid, self.server_port = owner_uid, port
        self.admission_scope = scope
        socketserver.TCPServer.__init__(self, str(path), Handler)
        self.origin, self.cookie_name = f'http://127.0.0.1:{port}', f'demo_session_{port}'

    def server_bind(self):
        self.socket.bind(self.server_address)

    def get_request(self):
        connection, address = self.socket.accept()
        if peer(connection)[1] != self.owner_uid:
            connection.close()
            raise PermissionError
        connection.settimeout(25)
        return connection, address


def main():
    os.umask(0o077)
    configuration = json.loads(Path('/admission/application.json').read_text())
    fields = {'subject', 'tenant', 'certificates', 'token', 'tenant_reference_key',
        'client_keys', 'expires_at', 'simulation', 'channel_token', 'controller_uid',
        'controller_gid', 'ui_port', 'admission_scope'}
    if set(configuration) != fields or type(configuration['simulation']) is not bool:
        raise ValueError
    until = time.monotonic() + 15
    while not Path('/channels/ready').exists():
        if time.monotonic() >= until:
            raise ValueError
        time.sleep(.05)
    client = ControlClient('/channels/control.sock', configuration['channel_token'],
                           controller_uid=configuration['controller_uid'])
    budget = RemoteBudget(client)
    simulation = configuration['simulation']
    redactor, agents = ChannelRedactor(client, simulation=simulation), {}
    for profile in ('financial', 'infrastructure'):
        identity = TrustedJWTIdentity(profile, issuer='https://fixture-issuer.invalid',
            audience='portfolio-local-composition', certificates=configuration['certificates'],
            snapshot_expires_at=configuration['expires_at'],
            subjects={configuration['subject']: SubjectGrant(configuration['tenant'],
                frozenset({'financial', 'infrastructure'}))},
            tenant_reference_key=bytes.fromhex(configuration['tenant_reference_key']))
        credential = ScopedCredential(profile, configuration['client_keys'][profile], configuration['expires_at'])
        gateway = ChannelGateway('http://127.0.0.1:14006', budget, credential,
            subject=configuration['subject'], profile=profile, redactor=redactor,
            transport=client.model_post, simulation=simulation)
        core = IntegratedCore(profile, identity, identity, identity, redactor, gateway,
            simulation=simulation, tools=ChannelTools(client, profile),
            audit_sink=RemoteAudit(client, 'tool'), terminal_sink=RemoteAudit(client, 'terminal'),
            providers=('simulated', 'stub') if simulation else ('google_sdp_context_candidate', 'vertex_gemini'))
        core.language_model_scope = profile == 'financial'
        agents[profile] = core, 'Bearer ' + configuration['token']
    composition = 'local_proxy_stub' if simulation else 'supervised_candidate_live'
    with UnixDemoServer('/ui/ui.sock', configuration['ui_port'], agents,
            RemoteOperations(client), composition, configuration['controller_uid'], configuration['admission_scope']) as server:
        os.chown('/ui/ui.sock', -1, configuration['controller_gid'])
        os.chmod('/ui/ui.sock', 0o660)
        server.serve_forever()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('isolated_application:blocked') from None
