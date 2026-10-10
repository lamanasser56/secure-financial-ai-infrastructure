"""Ops agent HTTP API (cluster-internal; only the front door may reach it, by NetworkPolicy and bearer key).

GET  /v1/health     liveness
GET  /v1/snapshot   timeline, pending approvals, denials, current findings
GET  /v1/posture    protective posture findings
POST /v1/execute    {"request_id", "approval"}: verify the owner's one-use token, execute once, verify
There is no endpoint to register targets, add actions or approve.
"""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time

from agent_platform import audit
from agent_platform.k8s import Client
from agent_platform.ops import registry
from agent_platform.ops.agent import Agent
from agent_platform.ops.approval import Verifier

SCAN_SECONDS = 15


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate')
        value[key] = item
    return value


class Handler(BaseHTTPRequestHandler):
    server_version, sys_version = 'ops-agent', ''

    def log_message(self, *_):
        pass

    def reply(self, status, value):
        raw = json.dumps(value, separators=(',', ':'), default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        return hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.server.api_key)

    def do_GET(self):
        if self.path == '/v1/health':
            self.reply(200, {'status': 'ok', 'targets': sorted(self.server.agent.targets)})
        elif not self.authorized():
            self.reply(403, {'code': 'FORBIDDEN'})
        elif self.path == '/v1/snapshot':
            self.reply(200, self.server.agent.snapshot())
        elif self.path == '/v1/posture':
            self.reply(200, self.server.agent.posture())
        else:
            self.reply(404, {'code': 'NOT_FOUND'})

    def do_POST(self):
        if self.path != '/v1/execute' or not self.authorized():
            self.reply(403, {'code': 'FORBIDDEN'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                raise ValueError('size')
            body = json.loads(self.rfile.read(size), object_pairs_hook=unique)
            if type(body) is not dict or set(body) != {'request_id', 'approval'} or not all(type(v) is str for v in body.values()):
                raise ValueError('shape')
        except ValueError:
            self.reply(400, {'code': 'INVALID_REQUEST'})
            return
        self.reply(200, self.server.agent.execute(body['request_id'], body['approval']))


def scanner(agent, stop):
    while not stop.is_set():
        try:
            agent.scan()
        except Exception as error:  # keep observing; never crash the API on a transient read error
            audit.emit('ops_scan_error', 'ops-agent', reason=type(error).__name__)
        stop.wait(SCAN_SECONDS)


def build(config_dir=Path('/secrets/ops'), registry_dir=Path('/registry')):
    config = json.loads((config_dir / 'ops.json').read_text(), object_pairs_hook=unique)
    if set(config) != {'api_key', 'approver_public_key', 'gateway_key', 'redactor_key'}:
        raise SystemExit('ops:config_rejected')
    explainer = None
    if config['gateway_key'] and config['redactor_key']:
        from agent_platform.ops.explain import Explainer
        from agent_platform.redaction import RedactorClient
        explainer = Explainer('http://gateway.platform.svc.cluster.local:4000', config['gateway_key'],
                              RedactorClient('http://redactor.platform.svc.cluster.local:4003', config['redactor_key']))
    agent = Agent(Client(), registry.load(registry_dir), Verifier(config['approver_public_key']), explainer=explainer)
    return agent, config['api_key']


def main():
    agent, api_key = build()
    stop = threading.Event()
    threading.Thread(target=scanner, args=(agent, stop), daemon=True).start()
    server = ThreadingHTTPServer(('0.0.0.0', 8090), Handler)
    server.daemon_threads, server.agent, server.api_key = True, agent, api_key
    audit.emit('ops_agent_started', 'ops-agent', targets=sorted(agent.targets), started_at=time.time())
    server.serve_forever()


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit('ops:arguments_rejected')
    main()
