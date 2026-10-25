"""Fixed in-cluster OpenAI-compatible assessment provider; never calls a model.

Only synthetic requests reach this process. It records bounded counters and
canary presence, never prompt or response content. Its sole answer is fixed.
"""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time


CANARIES = (b'synthetic-f1@example.test', b'+1 202-555-0101',
            b'+966 50 123 4567')
MAX_BODY = 32768
MAX_CALLS = 200


class Handler(BaseHTTPRequestHandler):
    server_version = 'assessment-provider-stub'
    sys_version = '1.0'

    def log_message(self, *_args):
        pass

    def send(self, status, value):
        raw = json.dumps(value, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/healthz':
            self.send(200, {'status': 'ok'})
        elif self.path == '/stats':
            with self.server.counter_lock:
                self.send(200, {'requests': self.server.requests,
                                'raw_canary_seen': self.server.raw_canary_seen})
        else:
            self.send(404, {'error': 'not_found'})

    def do_POST(self):
        if (self.path != '/v1/chat/completions'
                or self.headers.get('Content-Type', '').split(';')[0] != 'application/json'):
            self.send(404, {'error': 'not_found'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > MAX_BODY:
                raise ValueError('size')
            raw = self.rfile.read(size)
            value = json.loads(raw)
            if not isinstance(value, dict) or not isinstance(value.get('messages'), list):
                raise ValueError('shape')
            with self.server.counter_lock:
                if self.server.requests >= MAX_CALLS:
                    self.send(429, {'error': 'assessment_limit'})
                    return
                self.server.requests += 1
                number = self.server.requests
                self.server.raw_canary_seen |= any(canary in raw for canary in CANARIES)
            print(json.dumps({'audit_event': 'synthetic_provider_dispatch',
                              'seq': number, 'request_sha256': hashlib.sha256(raw).hexdigest(),
                              'raw_canary_present': self.server.raw_canary_seen,
                              'at': time.time()}, separators=(',', ':')), flush=True)
            self.send(200, {'id': 'chatcmpl-assessment-' + str(number),
                            'object': 'chat.completion', 'created': int(time.time()),
                            'model': 'assessment-stub',
                            'choices': [{'index': 0, 'message': {'role': 'assistant',
                                'content': '{"action":"answer","text":"Synthetic response."}'},
                                'finish_reason': 'stop'}],
                            'usage': {'prompt_tokens': 1, 'completion_tokens': 1,
                                      'total_tokens': 2}})
        except (ValueError, json.JSONDecodeError):
            self.send(400, {'error': 'invalid_synthetic_request'})


def make_server(host='0.0.0.0', port=8080):
    server = ThreadingHTTPServer((host, port), Handler)
    server.counter_lock = threading.Lock()
    server.requests = 0
    server.raw_canary_seen = False
    server.daemon_threads = True
    return server


if __name__ == '__main__':
    make_server().serve_forever()
