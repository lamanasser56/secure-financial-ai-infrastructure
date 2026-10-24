"""A redactor redirect must fail closed before a bearer key reaches the redirect destination."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import unittest

from agent_platform.redaction import RedactorClient
from runtime.phase3.trusted_runtime import ControlFailure


class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass


class Destination(QuietHandler):
    def do_GET(self):
        self.server.received.append(self.headers.get('Authorization'))
        self.send_response(200)
        self.send_header('Content-Length', '0')
        self.end_headers()


class Redirector(QuietHandler):
    def do_POST(self):
        self.server.received.append(self.headers.get('Authorization'))
        self.send_response(302)
        self.send_header('Location', self.server.destination)
        self.send_header('Content-Length', '0')
        self.end_headers()


class RedactorRedirect(unittest.TestCase):
    def test_cross_origin_redirect_does_not_forward_authorization(self):
        destination = HTTPServer(('127.0.0.1', 0), Destination)
        redirector = HTTPServer(('127.0.0.1', 0), Redirector)
        destination.received, redirector.received = [], []
        redirector.destination = 'http://127.0.0.1:%s/sink' % destination.server_port
        threads = [threading.Thread(target=server.serve_forever, daemon=True)
                   for server in (destination, redirector)]
        for thread in threads:
            thread.start()
        try:
            client = RedactorClient('http://127.0.0.1:%s' % redirector.server_port, 'k' * 64)
            with self.assertRaises(ControlFailure) as error:
                client.redact('synthetic input')
            self.assertEqual((error.exception.stage, error.exception.category),
                             ('presidio_anonymizer', 'unavailable'))
            self.assertEqual(redirector.received, ['Bearer ' + 'k' * 64])
            self.assertEqual(destination.received, [])
        finally:
            for server in (redirector, destination):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=10)
