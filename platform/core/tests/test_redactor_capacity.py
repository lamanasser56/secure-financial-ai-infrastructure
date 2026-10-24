"""Bounded, synthetic loopback requests exercise redactor capacity without a provider or cloud."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import threading
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace

from agent_platform.programs.redactor_server import Capacity, CapacityExceeded, Server, valid_client_keys


KEYS = {'app': 'a' * 64, 'ops': 'b' * 64, 'agent-test': 'c' * 64}


class BlockingProvider:
    def __init__(self):
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.count = self.active = self.peak = 0
        self.started = threading.Condition(self.lock)

    def wait_for(self, count):
        with self.started:
            return self.started.wait_for(lambda: self.count >= count, timeout=10)

    def redact(self, text):
        with self.started:
            self.count += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.started.notify_all()
        try:
            if not self.release.wait(10):
                raise TimeoutError('synthetic provider timeout')
            return SimpleNamespace(text=text, categories=())
        finally:
            with self.started:
                self.active -= 1


@contextmanager
def serving(provider, *, capacity, workers=8):
    server = Server(('127.0.0.1', 0), KEYS, SimpleNamespace(current=lambda: provider),
                    capacity=capacity, workers=workers)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        provider.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def request(server, client):
    url = 'http://127.0.0.1:%s/redact' % server.server_port
    message = urllib.request.Request(url, data=b'{"text":"synthetic"}', method='POST',
                                     headers={'Authorization': 'Bearer ' + KEYS[client],
                                              'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(message, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read()
        return error.code, json.loads(body) if body else {}


class RedactorCapacity(unittest.TestCase):
    def test_distinct_credentials_are_required_for_per_client_limits(self):
        self.assertTrue(valid_client_keys(KEYS))
        self.assertFalse(valid_client_keys({'app': 'a' * 64, 'ops': 'a' * 64}))

    def test_default_global_slot_matches_single_call_provider(self):
        capacity = Capacity(KEYS)
        with capacity.admit('app'):
            with self.assertRaises(CapacityExceeded):
                with capacity.admit('ops'):
                    pass

    def test_per_client_and_global_inflight_reject_without_provider_dispatch(self):
        provider = BlockingProvider()
        capacity = Capacity(KEYS, per_client=1, global_inflight=2, per_client_window=4, global_window=6)
        with serving(provider, capacity=capacity) as server, ThreadPoolExecutor(max_workers=2) as pool:
            app = pool.submit(request, server, 'app')
            self.assertTrue(provider.wait_for(1))
            self.assertEqual(request(server, 'app'), (429, {'code': 'CAPACITY_EXCEEDED'}))
            ops = pool.submit(request, server, 'ops')
            self.assertTrue(provider.wait_for(2))
            self.assertEqual(request(server, 'agent-test'), (429, {'code': 'CAPACITY_EXCEEDED'}))
            self.assertEqual(provider.count, 2)
            provider.release.set()
            self.assertEqual(app.result(timeout=10)[0], 200)
            self.assertEqual(ops.result(timeout=10)[0], 200)
            self.assertEqual(provider.peak, 2)

    def test_connection_worker_ceiling_rejects_before_starting_another_thread(self):
        provider = BlockingProvider()
        with serving(provider, capacity=Capacity(KEYS), workers=1) as server, ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(request, server, 'app')
            self.assertTrue(provider.wait_for(1))
            self.assertEqual(request(server, 'ops')[0], 503)
            self.assertEqual(provider.count, 1)
            provider.release.set()
            self.assertEqual(first.result(timeout=10)[0], 200)

    def test_per_client_and_global_window_ceiling_renews_without_resetting_active_work(self):
        now = [0.0]
        capacity = Capacity(KEYS, per_client=1, global_inflight=2, per_client_window=2, global_window=3,
                            window_seconds=60, clock=lambda: now[0])
        for _ in range(2):
            with capacity.admit('app'):
                pass
        with self.assertRaises(CapacityExceeded):
            with capacity.admit('app'):
                pass
        with capacity.admit('ops'):
            pass
        with self.assertRaises(CapacityExceeded):
            with capacity.admit('agent-test'):
                pass
        now[0] = 61.0
        with capacity.admit('app'):
            now[0] = 122.0
            with self.assertRaises(CapacityExceeded):
                with capacity.admit('app'):
                    pass  # the hour rolls, but an active client still owns its concurrency slot
        with capacity.admit('app'):
            pass
