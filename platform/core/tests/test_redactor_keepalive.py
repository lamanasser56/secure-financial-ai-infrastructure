"""Redactor: the Sensitive Data Protection channel stays usable after long idle (gRPC keepalive), offline.

The failure: the network path drops a TCP flow that is idle for about 10 minutes, silently (no FIN/RST), so the next
call waits out its 3 s deadline. Conntrack below reproduces that with a local TCP proxy in front of a real gRPC
server; the gRPC and SDK classes run only where grpcio / google-cloud-dlp are installed (requirements-google-sdp.txt).
"""
import importlib.util
import socket
import threading
import time
import types
import unittest
from unittest import mock

from agent_platform.programs import redactor_server

HAS_GRPC = importlib.util.find_spec('grpc') is not None
HAS_DLP = HAS_GRPC and importlib.util.find_spec('google.cloud.dlp_v2') is not None


class Options(unittest.TestCase):
    def test_keepalive_keeps_pinging_an_idle_channel_well_inside_the_drop(self):
        options = dict(redactor_server.KEEPALIVE_OPTIONS)
        self.assertLessEqual(options['grpc.keepalive_time_ms'], 600_000 // 5)  # several pings per 10-minute window
        self.assertEqual(options['grpc.keepalive_permit_without_calls'], 1)  # ping with no call in flight
        self.assertEqual(options['grpc.http2.max_pings_without_data'], 0)  # default 2: pinging would stop when idle
        self.assertEqual(options['grpc.use_local_subchannel_pool'], 1)  # a rebuild never reuses the old connection
        self.assertLess(options['grpc.keepalive_timeout_ms'], options['grpc.keepalive_time_ms'])

    def test_main_installs_the_keepalive_client_in_the_adapter(self):
        adapter = types.SimpleNamespace(_create_client=lambda: 'original')
        redactor_server.use_keepalive_client(adapter)
        self.assertIs(adapter._create_client, redactor_server.keepalive_client)
        source = (redactor_server.__file__ and open(redactor_server.__file__).read())
        main = source[source.index('def main():'):]
        self.assertLess(main.index('use_keepalive_client(google_sdp_adapter)'), main.index('Budget('))  # before any client

    def test_idle_rebuild_backstop_is_unchanged(self):
        self.assertEqual((redactor_server.IDLE_SECONDS, redactor_server.RETIRE_SECONDS), (120, 30))


class Conntrack:
    """TCP proxy: a flow with no byte either way for `idle_drop` seconds is dropped silently (bytes discarded,
    nothing closed), like VPC connection tracking. kill_all() drops every existing flow now."""

    def __init__(self, target_port, idle_drop):
        self.target, self.idle_drop, self.flows = target_port, idle_drop, []
        self.listener = socket.create_server(('127.0.0.1', 0))
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self.accept, daemon=True).start()

    def kill_all(self):
        for flow in self.flows:
            flow['dead'] = True

    def accept(self):
        while True:
            try:
                client, _ = self.listener.accept()
            except OSError:
                return
            upstream = socket.create_connection(('127.0.0.1', self.target))
            flow = {'last': time.monotonic(), 'dead': False}
            self.flows.append(flow)
            for a, b in ((client, upstream), (upstream, client)):
                threading.Thread(target=self.pipe, args=(a, b, flow), daemon=True).start()

    def pipe(self, a, b, flow):
        try:
            while data := a.recv(65536):
                now = time.monotonic()
                if now - flow['last'] >= self.idle_drop:
                    flow['dead'] = True
                if not flow['dead']:
                    flow['last'] = now
                    b.sendall(data)
        except OSError:
            return


def scaled(keepalive_ms, timeout_ms):
    """KEEPALIVE_OPTIONS with test-sized timings; every other option exactly as shipped."""
    times = {'grpc.keepalive_time_ms': keepalive_ms, 'grpc.keepalive_timeout_ms': timeout_ms}
    return [(k, times.get(k, v)) for k, v in redactor_server.KEEPALIVE_OPTIONS]


@unittest.skipUnless(HAS_GRPC, 'grpcio not installed (requirements-google-sdp.txt)')
class RealGrpc(unittest.TestCase):
    IDLE_DROP, IDLE = 3, 7  # the path drops a flow idle 3 s; the channel then sits idle 7 s

    def setUp(self):
        import grpc
        from concurrent import futures
        self.grpc = grpc
        self.server = grpc.server(futures.ThreadPoolExecutor(2), options=[
            ('grpc.http2.min_ping_interval_without_data_ms', 500), ('grpc.http2.max_ping_strikes', 0)])
        self.server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
            't.T', {'Echo': grpc.unary_unary_rpc_method_handler(lambda request, context: request)}),))
        port = self.server.add_insecure_port('127.0.0.1:0')
        self.server.start()
        self.addCleanup(self.server.stop, 0)
        self.proxy = Conntrack(port, self.IDLE_DROP)
        self.addCleanup(self.proxy.listener.close)

    def channel(self, options):
        channel = self.grpc.insecure_channel('127.0.0.1:%d' % self.proxy.port, options=options)
        self.addCleanup(channel.close)
        return channel

    def call(self, channel):
        try:
            channel.unary_unary('/t.T/Echo')(b'x', timeout=2)
            return 'OK'
        except self.grpc.RpcError as error:
            return error.code().name

    def test_without_keepalive_the_first_call_after_idle_hangs_to_its_deadline(self):
        channel = self.channel([])  # the SDK's defaults: the failure this fixes
        self.assertEqual(self.call(channel), 'OK')
        time.sleep(self.IDLE)
        self.assertEqual(self.call(channel), 'DEADLINE_EXCEEDED')

    def test_with_the_shipped_options_the_flow_never_goes_idle(self):
        channel = self.channel(scaled(keepalive_ms=1000, timeout_ms=800))
        self.assertEqual(self.call(channel), 'OK')
        time.sleep(self.IDLE)
        self.assertEqual(self.call(channel), 'OK')
        self.assertEqual(len(self.proxy.flows), 1)  # the same connection, kept alive

    def test_pinging_stops_without_unlimited_pings_and_the_flow_dies(self):
        options = [o for o in scaled(keepalive_ms=1000, timeout_ms=800) if o[0] != 'grpc.http2.max_pings_without_data']
        channel = self.channel(options)
        self.assertEqual(self.call(channel), 'OK')
        time.sleep(self.IDLE)
        self.assertEqual(self.call(channel), 'DEADLINE_EXCEEDED')

    def test_a_rebuilt_client_gets_its_own_connection_while_the_old_one_is_open(self):
        old = self.channel(scaled(keepalive_ms=60_000, timeout_ms=20_000))
        self.assertEqual(self.call(old), 'OK')
        time.sleep(1)
        self.proxy.kill_all()  # the old flow is gone, silently, and the old channel is still open (retired 30 s later)
        self.assertEqual(self.call(self.channel(scaled(keepalive_ms=60_000, timeout_ms=20_000))), 'OK')
        self.assertEqual(len(self.proxy.flows), 2)


@unittest.skipUnless(HAS_DLP, 'google-cloud-dlp not installed (requirements-google-sdp.txt)')
class SdkClient(unittest.TestCase):
    """The real DlpServiceClient as the adapter builds it; no request is sent (channels connect lazily)."""

    def build(self):
        import grpc
        from google.auth.credentials import AnonymousCredentials
        seen = []
        real = grpc.secure_channel

        def secure_channel(target, credentials, options=None, compression=None):
            seen.append((target, dict(options or ())))
            return real(target, credentials, options=options, compression=compression)
        with mock.patch('google.auth.default', return_value=(AnonymousCredentials(), None)), \
                mock.patch.object(grpc, 'secure_channel', side_effect=secure_channel):
            client = redactor_server.keepalive_client()
        self.addCleanup(client.transport.close)
        return client, seen

    def test_the_channel_carries_keepalive_and_the_sdk_defaults(self):
        from runtime.phase3.google_sdp_adapter import ENDPOINT
        client, seen = self.build()
        self.assertEqual(client.api_endpoint, ENDPOINT)
        [(target, options)] = seen
        self.assertEqual(target, ENDPOINT + ':443')
        for key, value in redactor_server.KEEPALIVE_OPTIONS:
            self.assertEqual(options[key], value)
        self.assertEqual((options['grpc.max_send_message_length'], options['grpc.max_receive_message_length']), (-1, -1))

    def test_the_adapter_counts_real_sdk_calls_with_the_keepalive_client(self):
        import grpc
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import dlp_v2
        from runtime.phase3 import google_sdp_adapter
        from runtime.phase3.sdp_context_policy import GoogleSDPContextRedactor
        with mock.patch.object(google_sdp_adapter, '_create_client', google_sdp_adapter._create_client):
            redactor_server.use_keepalive_client(google_sdp_adapter)
            with mock.patch('google.auth.default', return_value=(AnonymousCredentials(), None)), \
                    mock.patch.object(grpc, 'secure_channel', wraps=grpc.secure_channel) as secure_channel:
                adapter = GoogleSDPContextRedactor('demo-project-123456')
        self.addCleanup(adapter._client.transport.close)
        self.assertTrue(adapter.uses_real_sdk)  # operation_counts feed the daily ceiling
        self.assertIsInstance(adapter._client, dlp_v2.DlpServiceClient)
        self.assertEqual(dict(secure_channel.call_args.kwargs['options'])['grpc.http2.max_pings_without_data'], 0)


if __name__ == '__main__':
    unittest.main()
