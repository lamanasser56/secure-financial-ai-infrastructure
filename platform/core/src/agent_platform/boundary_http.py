"""Bounded HTTP for trusted mediators. No redirects, caller URLs, forwarded auth or content logs."""
from contextlib import contextmanager
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import urllib.request


class Rejected(Exception):
    def __init__(self, code, status=403):
        self.code, self.status = code, status


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate field')
        result[key] = value
    return result


def decode(raw):
    def invalid(_):
        raise ValueError('non-finite value')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_json(url, key, body, *, timeout=8):
    request = urllib.request.Request(url, data=json.dumps(body, allow_nan=False).encode(), method='POST',
                                     headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        raw = response.read((1 << 20) + 1)
        if response.status != 200 or len(raw) > 1 << 20:
            raise Rejected('UPSTREAM_UNAVAILABLE', 503)
        data = decode(raw)
        if type(data) is not dict:
            raise Rejected('UPSTREAM_UNAVAILABLE', 503)
        # The one explicitly supported response header; never relay cookies, auth or arbitrary headers.
        cost = response.headers.get('x-litellm-response-cost', '')
        headers = {'x-litellm-response-cost': cost} if len(cost) < 40 and cost.replace('.', '').isdigit() else {}
        return data, headers


class Clients:
    def __init__(self, keys, *, parallel=2, rpm=20, clock=time.monotonic):
        if not keys or len(set(keys.values())) != len(keys) or any(type(k) is not str or len(k) < 32 for k in keys.values()):
            raise ValueError('distinct client credentials required')
        self.keys, self.rpm, self.clock = dict(keys), rpm, clock
        self.slots = {name: threading.BoundedSemaphore(parallel) for name in keys}
        self.calls, self.lock = {}, threading.Lock()

    @contextmanager
    def admit(self, authorization):
        if type(authorization) is not str or len(authorization) > 256 or not authorization.isascii():
            raise Rejected('UNAUTHORIZED')
        principal = next((name for name, key in self.keys.items()
                          if hmac.compare_digest(authorization, 'Bearer ' + key)), None)
        if principal is None:
            raise Rejected('UNAUTHORIZED')
        with self.lock:
            now = self.clock()
            calls = self.calls[principal] = [t for t in self.calls.get(principal, []) if now - t < 60]
            if len(calls) >= self.rpm:
                raise Rejected('RATE_LIMITED', 429)
            calls.append(now)
        if not self.slots[principal].acquire(blocking=False):
            raise Rejected('BUSY', 429)
        try:
            yield principal
        finally:
            self.slots[principal].release()


class Handler(BaseHTTPRequestHandler):
    server_version, sys_version = 'agent-runtime-boundary', ''

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass

    def respond(self, status, value, headers=None):
        raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.respond(200 if self.path in ('/healthz', '/health/liveliness') else 404,
                     {'status': 'ok'} if self.path in ('/healthz', '/health/liveliness') else {'code': 'NOT_FOUND'})

    def do_POST(self):
        try:
            if (self.headers.get_all('Content-Length', []) != [self.headers.get('Content-Length')]
                    or self.headers.get('Transfer-Encoding') is not None
                    or self.headers.get('Content-Type') != 'application/json'
                    or len(self.headers.get_all('Authorization', [])) != 1):
                raise Rejected('REQUEST_REJECTED', 400)
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 32768:
                raise Rejected('REQUEST_REJECTED', 400)
            value = decode(self.rfile.read(length))
            result, headers = self.server.service.handle(self.path, self.headers.get('Authorization', ''), value)
            self.respond(200, result, headers)
        except Rejected as error:
            self.respond(error.status, {'code': error.code})
        except (ValueError, TypeError, TimeoutError):
            self.respond(400, {'code': 'REQUEST_REJECTED'})
        except Exception:
            self.respond(503, {'code': 'SERVICE_UNAVAILABLE'})


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, service, *, workers=8):
        super().__init__(address, Handler)
        self.service, self.slots = service, threading.BoundedSemaphore(workers)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b'HTTP/1.0 503 Busy\r\nContent-Length: 0\r\n\r\n')
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()
