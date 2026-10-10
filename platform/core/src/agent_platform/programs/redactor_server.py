#!/usr/bin/env python3
"""Redactor service for the qualified Sensitive Data Protection image (mounted read-only from a ConfigMap).

Persistent-platform form of the C redaction bridge: the same GoogleSDPContextRedactor class and policy file
(hash-checked), the same request/response contract (POST /redact {"text"} -> {"text","categories"}) and the
same size limits. Differences: client keys come from the mounted Secret (one per calling namespace) instead
of a one-window admission file, and the attempt budget renews per hour (174 SDK operations, the adapter's
maximum) with a daily ceiling. Any failure returns 503 and callers fail closed: no model request is sent.
"""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import time

APP_ROOT = Path('/app')
sys.path.insert(0, str(APP_ROOT))
POLICY_HASH = 'c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db'
WINDOW_SECONDS, WINDOW_OPERATIONS, DAILY_OPERATIONS = 3600, 174, 1740
MAX_TEXT_BYTES, MAX_BODY_BYTES = 4096, 16384


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate key')
        value[key] = item
    return value


def audit(event, **fields):
    print(json.dumps({'audit_event': event, 'component': 'redactor', 'at': time.time(), **fields},
                     separators=(',', ':')), flush=True)


class Budget:
    """Hourly window of SDK operations with a daily ceiling; a fresh adapter per window (construction is free)."""

    def __init__(self, factory, clock=time.time):
        self._factory, self._clock, self._lock = factory, clock, threading.Lock()
        self._window_start = self._day_start = clock()
        self._day_used = 0
        self.redactor = factory()

    def current(self):
        with self._lock:
            now = self._clock()
            if now - self._day_start >= 86400:
                self._day_start, self._day_used = now, 0
            if now - self._window_start >= WINDOW_SECONDS:
                self._day_used += sum(self.redactor.operation_counts.values())
                self._window_start, self.redactor = now, self._factory()
            if self._day_used + sum(self.redactor.operation_counts.values()) + 2 > DAILY_OPERATIONS:
                raise RuntimeError('daily budget')
            return self.redactor


class Handler(BaseHTTPRequestHandler):
    server_version, sys_version = 'redactor', ''

    def log_message(self, *_):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def reply(self, status, value):
        raw = json.dumps(value, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/healthz':
            self.reply(200, {'status': 'ok'})
        else:
            self.reply(405, {'code': 'METHOD_REJECTED'})

    def client(self):
        supplied = self.headers.get('Authorization', '')
        for name, key in self.server.keys.items():
            if hmac.compare_digest(supplied, 'Bearer ' + key):
                return name
        return None

    def do_POST(self):
        caller = self.client()
        if (self.path != '/redact' or caller is None or self.headers.get('Transfer-Encoding') is not None
                or self.headers.get('Content-Type') != 'application/json'):
            audit('redaction_rejected', reason='admission')
            self.reply(403, {'code': 'ADMISSION_REJECTED'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_BODY_BYTES:
                raise ValueError('size')
            raw = self.rfile.read(size)
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
            if (type(value) is not dict or set(value) != {'text'} or type(value['text']) is not str
                    or not 0 < len(value['text'].encode('utf-8')) <= MAX_TEXT_BYTES):
                raise ValueError('shape')
            result = self.server.budget.current().redact(value['text'])
            audit('redaction', caller=caller, categories=sorted(set(result.categories)))
            self.reply(200, {'text': result.text, 'categories': sorted(set(result.categories))})
        except Exception as error:  # provider/budget/input failure: fail closed, no content in logs
            audit('redaction_failed', caller=caller, reason=type(error).__name__)
            self.reply(503, {'code': 'REDACTION_UNAVAILABLE'})


def main():
    from runtime.phase3.google_sdp_adapter import ContentAttemptBudget
    from runtime.phase3.sdp_context_policy import GoogleSDPContextRedactor
    if hashlib.sha256((APP_ROOT / 'evaluation/google-sdp-context/policy.json').read_bytes()).hexdigest() != POLICY_HASH:
        raise SystemExit('redactor:policy_hash')
    project = os.environ['PORTFOLIO_PROJECT_ID']
    keys = json.loads(Path('/secrets/redactor/clients.json').read_text(), object_pairs_hook=unique)
    if set(keys) != {'app', 'ops'} or any(type(k) is not str or len(k) != 64 for k in keys.values()):
        raise SystemExit('redactor:client_keys')
    server = ThreadingHTTPServer(('0.0.0.0', 4003), Handler)
    server.daemon_threads = True
    server.keys = keys
    server.budget = Budget(lambda: GoogleSDPContextRedactor(project, budget=ContentAttemptBudget(WINDOW_OPERATIONS)))
    audit('redactor_started', policy_sha256=POLICY_HASH)
    server.serve_forever()


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit('redactor:arguments_rejected')
    os.umask(0o077)
    main()
