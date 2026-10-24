"""Mandatory trusted redaction boundary. Public credentials never authenticate directly to LiteLLM."""
import json
from pathlib import Path
import uuid

from agent_platform import audit, request_context
from agent_platform.boundary_http import Clients, Rejected, Server, request_json
from agent_platform.redaction import RedactorClient, WindowedBoundaryBudget
from runtime.phase3.deterministic_email import DeterministicEmailRedactor

UPSTREAM = 'http://gateway-provider.platform.svc.cluster.local:4001/v1/chat/completions'
ALIAS = 'secure-financial-chat'


class GatewayBoundary:
    def __init__(self, clients, redactor, *, dispatch=request_json):
        self.clients = Clients({name: value['external_key'] for name, value in clients.items()})
        self.upstream = {name: value['upstream_key'] for name, value in clients.items()}
        if set(self.clients.keys.values()) & set(self.upstream.values()):
            raise ValueError('public and provider credentials must be disjoint')
        self.redactor, self.dispatch = redactor, dispatch

    def handle(self, path, authorization, body):
        rid = uuid.uuid4().hex
        caller, outcome = None, 'REJECTED'
        try:
            with self.clients.admit(authorization) as caller, request_context.bind(rid):
                if path != '/v1/chat/completions' or type(body) is not dict:
                    raise Rejected('ROUTE_REJECTED', 400)
                allowed = {'model', 'messages', 'temperature', 'max_tokens', 'stream', 'response_format', 'metadata', 'timeout'}
                if (set(body) - allowed or body.get('model') != ALIAS or body.get('stream', False) is not False
                        or type(body.get('max_tokens')) is not int or not 1 <= body['max_tokens'] <= 1024
                        or body.get('temperature', 0) != 0
                        or body.get('response_format') != {'type': 'json_object'}):
                    raise Rejected('MODEL_REQUEST_REJECTED', 400)
                if 'timeout' in body and (caller != 'ops-explain' or type(body['timeout']) is not int or body['timeout'] != 20):
                    raise Rejected('TIMEOUT_OVERRIDE_REJECTED', 400)
                messages = body.get('messages')
                if type(messages) is not list or not 1 <= len(messages) <= 8:
                    raise Rejected('MESSAGES_REJECTED', 400)
                clean, size = [], 0
                for message in messages:
                    if (type(message) is not dict or set(message) != {'role', 'content'}
                            or message['role'] not in ('system', 'user', 'assistant')
                            or type(message['content']) is not str or not message['content']
                            or len(message['content'].encode()) > 4096):
                        raise Rejected('MESSAGES_REJECTED', 400)
                    size += len(message['content'].encode())
                    if size > 12000:
                        raise Rejected('MESSAGES_REJECTED', 400)
                    try:
                        redacted = self.redactor.redact(message['content'])
                    except Exception:
                        raise Rejected('REDACTION_UNAVAILABLE', 503) from None
                    clean.append({'role': message['role'], 'content': redacted.text})
                forwarded = {k: v for k, v in body.items() if k != 'metadata'}
                forwarded['messages'], forwarded['metadata'] = clean, {'request_id': rid}
                try:
                    result = self.dispatch(UPSTREAM, self.upstream[caller], forwarded, timeout=25 if caller == 'ops-explain' else 8)
                except Exception:
                    raise Rejected('MODEL_UNAVAILABLE', 503) from None
                outcome = 'DISPATCHED_REDACTED'
                return result
        finally:
            audit.emit('gateway_boundary', 'gateway-boundary', request_id=rid, caller=caller, outcome=outcome)


def main():
    config = json.loads(Path('/secrets/gateway-boundary/boundary.json').read_text())
    redactor = DeterministicEmailRedactor(RedactorClient('http://redactor.platform.svc.cluster.local:4003',
                                                       config['redactor_key'], budget=WindowedBoundaryBudget()))
    Server(('0.0.0.0', 4000), GatewayBoundary(config['clients'], redactor)).serve_forever()


if __name__ == '__main__':
    main()
