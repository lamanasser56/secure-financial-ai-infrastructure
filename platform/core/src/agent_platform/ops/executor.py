"""Independent approval-verifying mutation authority. Only this workload receives Kubernetes patch rights."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import threading

from agent_platform.boundary_http import Clients, Rejected, Server, request_json
from agent_platform.k8s import Client
from agent_platform.ops import approval, registry
from agent_platform.ops.agent import Agent, REQUEST_ID

URL = 'http://ops-executor.ops.svc.cluster.local:8091/execute'


class ExecutorClient:
    def __init__(self, key, *, dispatch=request_json):
        self.key, self.dispatch = key, dispatch

    def execute(self, proposal, token):
        result, _ = self.dispatch(URL, self.key, {'proposal': proposal, 'approval': token}, timeout=195)
        return result


class ReplayStore:
    """Commit consumption before mutation; persist across broker restarts. Storage failure fails closed."""
    def __init__(self, path):
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS used (request_id TEXT PRIMARY KEY)')

    def consume(self, request_id):
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute('PRAGMA synchronous=FULL')
            try:
                db.execute('INSERT INTO used VALUES (?)', (request_id,))
                return True
            except sqlite3.IntegrityError:
                return False


class Executor:
    def __init__(self, client, targets, public_key, api_key, *, replay_store, verify_kwargs=None):
        self.clients = Clients({'ops': api_key})
        self.lock = threading.Lock()
        self.agent = Agent(client, targets, approval.Verifier(public_key, nonce_store=replay_store),
                           verify_kwargs=verify_kwargs, component='ops-executor')

    def handle(self, path, authorization, body):
        with self.clients.admit(authorization):
            if path != '/execute' or type(body) is not dict or set(body) != {'proposal', 'approval'}:
                raise Rejected('REQUEST_REJECTED', 400)
            p = body['proposal']
            required = {'request_id', 'target', 'action', 'arguments', 'args_digest', 'evidence_digest', 'uid',
                        'resource_version', 'finding', 'created_at', 'expires_at', 'state'}
            if (type(p) is not dict or set(p) - (required | {'explanation'}) or not required <= set(p)
                    or type(p['target']) is not str or p['target'] not in self.agent.targets
                    or self.agent.targets[p['target']].observe_only or type(p['action']) is not str or p['action'] not in registry.ACTIONS
                    or type(p['arguments']) is not dict or p['args_digest'] != approval.args_digest(p['arguments'])
                    or type(p['request_id']) is not str or not REQUEST_ID.fullmatch(p['request_id'])):
                raise Rejected('PROPOSAL_REJECTED', 400)
            # Authenticate the signature/binding before inserting into executor state; engine consumes durably
            # and freshly diagnoses before its single patch. Unbound UI/state fields never become authoritative.
            try:
                claims = self.agent.verifier.verify(body['approval'], p)
            except Exception:
                raise Rejected('APPROVAL_REJECTED') from None
            trusted = {**{k: claims[k] for k in approval.BOUND}, 'arguments': copy.deepcopy(p['arguments']),
                       'finding': 'APPROVED', 'created_at': claims['issued_at'], 'expires_at': claims['expires_at'], 'state': 'proposed'}
            # Serialize registration+execution; owner tokens are still one-use and must match freshly read evidence.
            with self.lock:
                self.agent.proposals[p['request_id']] = trusted
                return self.agent.execute(p['request_id'], body['approval']), {}


def main():
    os.umask(0o077)
    config = json.loads(Path('/secrets/executor/executor.json').read_text())
    service = Executor(Client(), registry.load(), config['approver_public_key'], config['api_key'],
                       replay_store=ReplayStore('/state/approvals.sqlite'))
    Server(('0.0.0.0', 8091), service).serve_forever()


if __name__ == '__main__':
    main()
