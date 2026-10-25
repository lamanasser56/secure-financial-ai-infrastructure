"""Owner-injected compromised-worker probe, used temporarily by make attack, never a production endpoint.

Runs in the existing signed Financial image with that worker's normal credentials. A real frontdoor
turn keeps its capability active while the coordinator exercises the live broker. Raw capabilities
are returned only over the worker-authenticated operator channel and must never enter evidence/logs.
"""
import json
import re
from pathlib import Path
import threading
import urllib.error
import urllib.request
import uuid

from agent_platform.boundary_http import Clients, Rejected, Server
from agent_platform.data_capability import CapabilityVerifier, b64, canonical, unb64
from finance_agent.data_broker import URL as BROKER


def http(url, key, body):
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    except (OSError, ValueError):
        return 0, {'code': 'TRANSPORT_ERROR'}
    with response:
        try:
            raw = response.read(65537)
            value = json.loads(raw) if len(raw) <= 65536 else None
            return (response.code, value) if isinstance(value, dict) else (0, {'code': 'INVALID_REPLY'})
        except (ValueError, OSError):
            return 0, {'code': 'INVALID_REPLY'}


class Probe:
    def __init__(self, config, *, broker=BROKER, dispatch=http, hold=45):
        self.config, self.broker, self.dispatch, self.hold = config, broker, dispatch, hold
        self.clients = Clients({'frontdoor': config['worker_key']}, parallel=4, rpm=120)
        self.verifier = CapabilityVerifier(config['capability_public_key'])
        self.lock, self.finished = threading.Lock(), threading.Event()
        self.token, self.summary = None, None

    def handle(self, path, authorization, body):
        with self.clients.admit(authorization):
            if path == '/ask':
                if type(body) is not dict or set(body) != {'capability', 'question', 'language'}:
                    raise Rejected('REQUEST_REJECTED', 400)
                claims = self.verifier.verify(body['capability'], self.config['agent_name'])
                if claims['user'] != self.config['user_id']:
                    raise Rejected('USER_BINDING_REJECTED')
                with self.lock:
                    if self.token is not None:
                        raise Rejected('BUSY', 429)
                    self.token, self.summary = body['capability'], None
                    self.finished.clear()
                try:
                    completed = self.finished.wait(self.hold)
                    return {'status': 'probe_complete' if completed else 'probe_timeout', 'probe': self.summary}, {}
                finally:
                    with self.lock:
                        self.token = None
            if path != '/probe' or type(body) is not dict:
                raise Rejected('REQUEST_REJECTED', 400)
            operation = body.get('operation')
            if operation == 'active' and set(body) == {'operation'}:
                with self.lock:
                    return {'capability': self.token}, {}
            if operation == 'finish' and set(body) == {'operation'}:
                self.finished.set()
                return {'finished': True}, {}
            if operation != 'exercise' or set(body) != {'operation', 'foreign', 'own_marker', 'foreign_marker', 'month'}:
                raise Rejected('REQUEST_REJECTED', 400)
            if (type(body['foreign']) is not str or len(body['foreign']) > 2048
                    or any(type(body[k]) is not str or not 0 < len(body[k]) <= 80 for k in ('own_marker', 'foreign_marker'))
                    or type(body['month']) is not str or not re.fullmatch(r'20[2-3][0-9]-(0[1-9]|1[0-2])',body['month'])):
                raise Rejected('REQUEST_REJECTED', 400)
            with self.lock:
                token = self.token
            if token is None:
                raise Rejected('NO_ACTIVE_TURN', 409)
            self.summary = self.exercise(token, body)
            return self.summary, {}

    def exercise(self, token, supplied):
        def call(capability, tool='find_transactions', args=None):
            return self.dispatch(self.broker, self.config['broker_key'], {'capability': capability,
                'tool': tool, 'args': {'month': supplied['month']} if args is None else args})
        def own():
            status, value = call(token)
            text = json.dumps(value)
            leaked=supplied['foreign_marker'] in text
            return (status == 200 and type(value.get('transactions')) is list
                    and supplied['own_marker'] in text and not leaked),leaked
        before,before_leak = own()
        foreign = call(supplied['foreign'])
        raw, signature = token.split('.')
        claims = json.loads(unb64(raw))
        claims['user'] = str(uuid.uuid4())
        forged = call(b64(canonical(claims)) + '.' + signature)
        identity = call(token, args={'month': supplied['month'], 'user_id': str(uuid.uuid4())})
        write = call(token, tool='delete_expenses')
        after,after_leak = own()
        required = {'gateway_key', 'redactor_key', 'agent_name', 'broker_key', 'worker_key', 'capability_public_key', 'user_id'}
        minimal = set(self.config) == required and all(type(v) is str and 'PRIVATE KEY' not in v
                    and 'postgresql://' not in v for v in self.config.values())
        evidence = {'worker_credentials_minimal': minimal, 'own_before': before, 'own_after': after,
            'foreign_active_capability': foreign == (403, {'code': 'CAPABILITY_REJECTED'}),
            'forged_user': forged == (403, {'code': 'CAPABILITY_REJECTED'}),
            'extra_identity': identity == (400, {'code': 'ARGUMENTS_REJECTED'}),
            'write_tool': write == (400, {'code': 'TOOL_REJECTED'})}
        unavailable = not before or not after or any(status == 0 or status == 429 or status >= 500
                                                     for status, _ in (foreign, forged, identity, write))
        breach=not minimal or before_leak or after_leak or any(status==200 for status,_ in (foreign,forged,identity,write))
        return {'verdict': 'FAIL' if breach else 'NOT_EXERCISED' if unavailable else 'PASS' if all(evidence.values()) else 'FAIL', 'checks': evidence}


if __name__ == '__main__':
    config = json.loads(Path('/secrets/agent/agent.json').read_text())
    Server(('0.0.0.0', 8081), Probe(config)).serve_forever()
