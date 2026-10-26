#!/usr/bin/env python3
"""Redactor service for the qualified Sensitive Data Protection image (owned by its signed service image).

Persistent-platform form of the C redaction bridge: the same GoogleSDPContextRedactor class and policy file
(hash-checked), the same request/response contract (POST /redact {"text"} -> {"text","categories"}) and the
same size limits. Differences: client keys come from the mounted Secret (one per calling namespace) instead
of a one-window admission file, and the attempt budget renews per hour (174 SDK operations, the adapter's
maximum) with a daily ceiling. Server-owned per-key/global request and concurrency ceilings protect the
shared service; failures remain closed, so no model request is sent.
"""
import hashlib
import hmac
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from pathlib import Path
import sys
import threading
import time

from .phone_guard import mask_phones

from runtime.phase3.sdp_context_policy import DIRECTORY as POLICY_DIRECTORY
POLICY_HASH = 'c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db'
WINDOW_SECONDS, WINDOW_OPERATIONS, DAILY_OPERATIONS = 3600, 174, 1740
CLIENT_REQUESTS_PER_WINDOW = 40
GLOBAL_REQUESTS_PER_WINDOW = WINDOW_OPERATIONS // 2  # the adapter can spend two SDK operations per request
CLIENT_INFLIGHT, GLOBAL_INFLIGHT, SERVER_WORKERS = 1, 1, 8  # the adapter itself admits one call at a time
IDLE_SECONDS = 120  # backstop: rebuild the provider client after this long without a call
# gRPC keepalive on the Sensitive Data Protection channel. The network path drops a TCP flow that is idle for about
# 10 minutes without telling either end, so the next call waits out its 3 s deadline and fails closed. A ping every
# 60 s keeps the flow from going idle. max_pings_without_data=0 is required: by default gRPC stops pinging after two
# pings with no call in between, and the flow then goes stale anyway. A local subchannel pool gives every rebuilt
# client its own connection, so a rebuild never reuses the old one. If the server ever refuses the ping rate, it
# closes the connection with GOAWAY (the client reconnects on the next call; it does not hang).
KEEPALIVE_OPTIONS = (('grpc.keepalive_time_ms', 60_000), ('grpc.keepalive_timeout_ms', 20_000),
                     ('grpc.keepalive_permit_without_calls', 1), ('grpc.http2.max_pings_without_data', 0),
                     ('grpc.use_local_subchannel_pool', 1))
RETIRE_SECONDS = 30  # a replaced client is closed after this delay: longer than the adapter's 8 s overall deadline
MAX_TEXT_BYTES, MAX_BODY_BYTES = 4096, 16384
REQUEST_ID = re.compile(r'[0-9a-f]{32}')  # the caller's X-Request-ID; any other value is dropped


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


class CapacityExceeded(Exception):
    """An authenticated request exceeded a server-owned capacity ceiling."""


class Capacity:
    """Atomic per-client and global request/in-flight ceilings, shared by all HTTP workers."""

    def __init__(self, clients, *, per_client=CLIENT_INFLIGHT, global_inflight=GLOBAL_INFLIGHT,
                 per_client_window=CLIENT_REQUESTS_PER_WINDOW, global_window=GLOBAL_REQUESTS_PER_WINDOW,
                 window_seconds=WINDOW_SECONDS, clock=time.monotonic):
        if (not clients or min(per_client, global_inflight, per_client_window, global_window, window_seconds) <= 0):
            raise ValueError('capacity:limits')
        self._clients = frozenset(clients)
        self._per_client, self._global_inflight = per_client, global_inflight
        self._per_client_window, self._global_window = per_client_window, global_window
        self._window_seconds, self._clock = window_seconds, clock
        self._start = clock()
        self._used = self._active = 0
        self._client_used = {client: 0 for client in clients}
        self._client_active = {client: 0 for client in clients}
        self._lock = threading.Lock()

    @contextmanager
    def admit(self, client):
        with self._lock:
            if client not in self._clients:
                raise CapacityExceeded()
            now = self._clock()
            if now - self._start >= self._window_seconds:
                self._start, self._used = now, 0
                self._client_used = {name: 0 for name in self._clients}
            if (self._active >= self._global_inflight or self._client_active[client] >= self._per_client
                    or self._used >= self._global_window or self._client_used[client] >= self._per_client_window):
                raise CapacityExceeded()
            self._active += 1
            self._client_active[client] += 1
            self._used += 1
            self._client_used[client] += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
                self._client_active[client] -= 1


class Budget:
    """Hourly window of SDK operations with a daily ceiling.

    The adapter owns one gRPC channel to the Sensitive Data Protection endpoint, kept alive by KEEPALIVE_OPTIONS. As
    a backstop, the adapter is also rebuilt after IDLE_SECONDS without a call (construction is free: no request is
    sent). The window's attempt budget object is shared by every adapter of the window, so a rebuild never renews it.
    """

    def __init__(self, factory, new_window, clock=time.time, idle_seconds=IDLE_SECONDS, retire_seconds=RETIRE_SECONDS):
        self._factory, self._new_window, self._clock = factory, new_window, clock
        self._idle_seconds, self._retire_seconds, self._lock = idle_seconds, retire_seconds, threading.Lock()
        self._window_start = self._day_start = self._last_used = clock()
        self._day_used = 0
        self._window = new_window()
        self.redactor = factory(self._window)

    def _replace(self):
        old, self.redactor = self.redactor, self._factory(self._window)
        timer = threading.Timer(self._retire_seconds, self._release, (old,))
        timer.daemon = True  # best effort: never blocks shutdown
        timer.start()

    @staticmethod
    def _release(redactor):
        """Close the replaced adapter's gRPC channel so rebuilds do not accumulate sockets (errors are ignored)."""
        try:
            transport = getattr(getattr(redactor, '_client', None), 'transport', None)
            close = getattr(transport, 'close', None)
            if callable(close):
                close()
        except Exception:
            pass

    def current(self):
        with self._lock:
            now = self._clock()
            if now - self._day_start >= 86400:
                self._day_start, self._day_used = now, 0
            if now - self._window_start >= WINDOW_SECONDS:
                self._day_used += sum(self.redactor.operation_counts.values())
                self._window_start, self._window = now, self._new_window()
                self._replace()
            elif now - self._last_used >= self._idle_seconds:
                self._day_used += sum(self.redactor.operation_counts.values())
                self._replace()  # fresh channel, same attempt budget
            self._last_used = now
            if self._day_used + sum(self.redactor.operation_counts.values()) + 2 > DAILY_OPERATIONS:
                raise RuntimeError('daily budget')
            return self.redactor


def keepalive_client():
    """Construct the SDK through its normal transport configuration; no request is sent."""
    from runtime.phase3.google_sdp_adapter import _create_client
    return _create_client(KEEPALIVE_OPTIONS)


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
        if not supplied.isascii():
            return None
        for name, key in self.server.keys.items():
            if hmac.compare_digest(supplied, 'Bearer ' + key):
                return name
        return None

    def request_id(self):
        value = self.headers.get('X-Request-ID', '')
        return value if REQUEST_ID.fullmatch(value) else None

    def do_POST(self):
        caller = self.client()
        rid = self.request_id()
        if (self.path != '/redact' or caller is None or self.headers.get('Transfer-Encoding') is not None
                or self.headers.get('Content-Type') != 'application/json'):
            audit('redaction_rejected', reason='admission')
            self.reply(403, {'code': 'ADMISSION_REJECTED'})
            return
        try:
            with self.server.capacity.admit(caller):
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_BODY_BYTES:
                    raise ValueError('size')
                raw = self.rfile.read(size)
                value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
                if (type(value) is not dict or set(value) != {'text'} or type(value['text']) is not str
                        or not 0 < len(value['text'].encode('utf-8')) <= MAX_TEXT_BYTES):
                    raise ValueError('shape')
                locally_masked, phone_found = mask_phones(value['text'])
                result = self.server.budget.current().redact(locally_masked)
                categories = sorted(set(result.categories) | ({'PHONE_NUMBER'} if phone_found else set()))
                audit('redaction', caller=caller, categories=categories, request_id=rid)
                self.reply(200, {'text': result.text, 'categories': categories})
        except CapacityExceeded:
            audit('redaction_rejected', caller=caller, reason='capacity', request_id=rid)
            self.reply(429, {'code': 'CAPACITY_EXCEEDED'})
        except Exception as error:  # provider/budget/input failure: fail closed, no content in logs
            audit('redaction_failed', caller=caller, reason=type(error).__name__, request_id=rid,
                  diagnostic=getattr(error, 'diagnostic', None))  # finite constants only (adapter contract)
            self.reply(503, {'code': 'REDACTION_UNAVAILABLE'})


class Server(ThreadingHTTPServer):
    """Bound the number of connection threads, including unauthenticated or stalled clients."""

    daemon_threads = True

    def __init__(self, address, keys, budget, *, capacity=None, workers=SERVER_WORKERS):
        if workers <= 0:
            raise ValueError('capacity:workers')
        super().__init__(address, Handler)
        self.keys, self.budget = keys, budget
        self.capacity = capacity or Capacity(keys)
        self._workers = threading.BoundedSemaphore(workers)

    def process_request(self, request, client_address):
        if not self._workers.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._workers.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._workers.release()


def valid_client_keys(keys):
    """Each named client must have its own key for per-client limits to be meaningful."""
    return (type(keys) is dict and {'app', 'ops'} <= set(keys)
            and all(type(c) is str and (c in ('app', 'ops', 'gateway-boundary')
                                        or re.fullmatch(r'agent-[a-z][a-z0-9-]{1,20}[a-z0-9]', c))
                    for c in keys)
            and all(type(key) is str and len(key) == 64 for key in keys.values())
            and len(set(keys.values())) == len(keys))


def main():
    from runtime.phase3.google_sdp_adapter import ContentAttemptBudget
    from runtime.phase3.sdp_context_policy import GoogleSDPContextRedactor
    if hashlib.sha256((POLICY_DIRECTORY / 'policy.json').read_bytes()).hexdigest() != POLICY_HASH:
        raise SystemExit('redactor:policy_hash')
    project = os.environ['PORTFOLIO_PROJECT_ID']
    keys = json.loads(Path('/secrets/redactor/clients.json').read_text(), object_pairs_hook=unique)
    # One key per calling namespace: the front door (app), the ops agent (ops) and each onboarded agent (agent-<name>).
    if not valid_client_keys(keys):
        raise SystemExit('redactor:client_keys')
    server = Server(('0.0.0.0', 4003), keys,
                    Budget(lambda budget: GoogleSDPContextRedactor(project, budget=budget, grpc_options=KEEPALIVE_OPTIONS),
                           lambda: ContentAttemptBudget(WINDOW_OPERATIONS)))
    audit('redactor_started', policy_sha256=POLICY_HASH)
    server.serve_forever()


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit('redactor:arguments_rejected')
    os.umask(0o077)
    main()
