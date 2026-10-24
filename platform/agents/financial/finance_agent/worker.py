"""Untrusted Financial worker RPC. User context comes from the trusted frontdoor; data access stays in the broker."""
import json
from pathlib import Path

from agent_platform.boundary_http import Clients, Rejected, Server
from agent_platform.data_capability import CapabilityVerifier
from agent_platform.redaction import RedactorClient, WindowedBoundaryBudget
from finance_agent.agent import FinanceAgent, Gateway
from finance_agent.data_broker import RemoteStore
from runtime.phase3.deterministic_email import DeterministicEmailRedactor


class Worker:
    def __init__(self, name, key, public_key, agent, store, *, user_id):
        self.name, self.clients, self.verifier = name, Clients({'frontdoor': key}), CapabilityVerifier(public_key)
        self.agent, self.store, self.user_id = agent, store, user_id

    def handle(self, path, authorization, body):
        with self.clients.admit(authorization):
            fields = {'capability'} if path == '/forget' else {'capability', 'question', 'language'}
            if path not in ('/ask', '/forget') or type(body) is not dict or set(body) != fields:
                raise Rejected('REQUEST_REJECTED', 400)
            claims = self.verifier.verify(body['capability'], self.name)
            if claims['user'] != self.user_id:
                raise Rejected('USER_BINDING_REJECTED')
            if path == '/forget':
                self.agent.forget(claims['user'])
                return {'status':'forgotten'}, {}
            with self.store.scope(body['capability'], claims):
                return self.agent.ask(claims['user'], body['question'], body['language']), {}


def build(config):
    required = {'gateway_key', 'redactor_key', 'agent_name', 'broker_key', 'worker_key', 'capability_public_key', 'user_id'}
    if set(config) != required:
        raise ValueError('worker config rejected; legacy database/session credentials forbidden')
    store = RemoteStore(config['broker_key'])
    redactor = DeterministicEmailRedactor(RedactorClient('http://redactor.platform.svc.cluster.local:4003',
                                                       config['redactor_key'], budget=WindowedBoundaryBudget()))
    # This trace is worker-produced, not the trusted broker's independent data-access event.
    agent = FinanceAgent(store, redactor, Gateway(config['gateway_key']), audit_key=config['broker_key'].encode())
    return Worker(config['agent_name'], config['worker_key'], config['capability_public_key'], agent, store, user_id=config['user_id'])


def main():
    Server(('0.0.0.0', 8081), build(json.loads(Path('/secrets/agent/agent.json').read_text()))).serve_forever()


if __name__ == '__main__':
    main()
