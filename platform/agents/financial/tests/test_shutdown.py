"""SIGTERM: the Financial Agent's server stops fast and cleanly (it runs as PID 1, which ignores SIGTERM by default).

Each test runs the real Server + serve() in a child process and sends it a real SIGTERM.
"""
import http.client
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import unittest

REPO = Path(__file__).resolve().parents[4]
CHILD = r'''
import sys, time
from http.server import BaseHTTPRequestHandler
from finance_agent import server

class Slow(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(float(self.path.strip('/') or 0))
        self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'ok')
    def log_message(self, *args):
        pass

httpd = server.Server(('127.0.0.1', 0), Slow)
print(httpd.server_address[1], flush=True)
print('drained' if server.serve(httpd, drain_seconds=float(sys.argv[1])) else 'cut', flush=True)
'''


class Shutdown(unittest.TestCase):
    def start(self, drain_seconds):
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(str(REPO / p) for p in ('platform/agents/financial', 'platform/core/src', '.')))
        child = subprocess.Popen([sys.executable, '-B', '-c', CHILD, str(drain_seconds)], stdout=subprocess.PIPE, text=True, env=env)
        self.addCleanup(lambda: child.poll() is None and child.kill())
        return child, int(child.stdout.readline())

    def get(self, port, path, out):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        connection.request('GET', path)
        response = connection.getresponse()
        out.append((response.status, response.read()))

    def test_idle_server_exits_at_once_on_sigterm(self):
        child, port = self.start(10)
        self.get(port, '/0', [])
        started = time.monotonic()
        child.send_signal(signal.SIGTERM)
        self.assertEqual(child.wait(timeout=5), 0)
        self.assertLess(time.monotonic() - started, 5)  # locally ~0.5 s; well under the 30 s grace period
        self.assertEqual(child.stdout.read().strip(), 'drained')

    def test_in_flight_request_finishes_and_new_connections_are_refused(self):
        child, port = self.start(10)
        answers = []
        slow = threading.Thread(target=self.get, args=(port, '/1.0', answers))
        slow.start()
        time.sleep(0.3)  # the slow request is in flight
        child.send_signal(signal.SIGTERM)
        self.assertEqual(child.wait(timeout=5), 0)
        slow.join(5)
        self.assertEqual(answers, [(200, b'ok')])
        self.assertEqual(child.stdout.read().strip(), 'drained')
        with self.assertRaises(OSError):
            self.get(port, '/0', [])

    def test_drain_is_bounded(self):
        child, port = self.start(0.5)
        threading.Thread(target=self.get, args=(port, '/30', []), daemon=True).start()
        time.sleep(0.3)
        started = time.monotonic()
        child.send_signal(signal.SIGTERM)
        self.assertEqual(child.wait(timeout=5), 0)
        # Locally ~0.75 s (one 0.5 s poll + the 0.5 s drain); a busy CI runner once took 4.0 s. The bound only has to
        # prove the process did not wait for the 30 s request or the Pod's 30 s grace period.
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(child.stdout.read().strip(), 'cut')


if __name__ == '__main__':
    unittest.main()
