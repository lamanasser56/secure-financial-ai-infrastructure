"""Bounded, peer-checked local channel. No remote URL, command or file selector.

Only the trusted supervisor implements operations. Container clients receive no
database, administrative, issuer-private or cloud credential. This is not a
defence against compromise of the trusted supervisor or the worker kernel.
"""
import hmac
import json
import os
from pathlib import Path
import socket
import socketserver
import struct
import threading

from runtime.agents.operations import OperationsBlocked
from runtime.agents.terminal_diagnostics import BudgetAdmissionFailure, BUDGET_REASONS, terminal_failure
from runtime.phase3.trusted_runtime import ControlFailure

LIMIT = 32768


def encode(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    if not 0 < len(raw) <= LIMIT:
        raise ControlFailure('structured_input_validation', 'invalid_request')
    return raw


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def receive(sock):
    def exact(count):
        result = bytearray()
        while len(result) < count:
            piece = sock.recv(count - len(result))
            if not piece:
                raise ValueError
            result.extend(piece)
        return bytes(result)
    size = struct.unpack('!I', exact(4))[0]
    if not 0 < size <= LIMIT:
        raise ValueError
    return decode(exact(size))


def send(sock, value):
    raw = encode(value)
    sock.sendall(struct.pack('!I', len(raw)) + raw)


def peer(sock):
    return struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))


class ControlClient:
    def __init__(self, path, token, *, controller_uid):
        if type(token) is not str or len(token) != 64 or not 0 <= controller_uid < 65536:
            raise ValueError
        self.path, self.token, self.uid = str(path), token, controller_uid
        self.sequence, self._lock, self.permit = 0, threading.RLock(), None

    def call(self, operation, value):
        with self._lock:
            self.sequence += 1
            try:
                with socket.socket(socket.AF_UNIX) as connection:
                    connection.settimeout(25)
                    connection.connect(self.path)
                    if peer(connection)[1] != self.uid:
                        raise ValueError
                    send(connection, {'schema_version': 1, 'token': self.token,
                        'sequence': self.sequence, 'operation': operation, 'value': value})
                    response = receive(connection)
            except Exception:
                raise ControlFailure('audit', 'unavailable') from None
            if type(response) is not dict or set(response) not in ({'result'}, {'failure'}):
                raise ControlFailure('audit', 'invalid_event')
            if 'failure' in response:
                failure = response['failure']
                if failure.get('kind') == 'operations':
                    raise OperationsBlocked(failure.get('reason'))
                if failure.get('reason') in BUDGET_REASONS:
                    raise BudgetAdmissionFailure(failure['reason'])
                raise ControlFailure(failure.get('stage', 'audit'), failure.get('reason', 'invalid_event'))
            return response['result']

    def model_post(self, url, body, timeout, *, headers):
        # The trusted side fixes the destination and checks the scoped key.
        permit, self.permit = self.permit, None
        return self.call('model', {'permit': permit, 'body': body,
                                  'authorization': headers.get('Authorization')})


class ControlServer(socketserver.UnixStreamServer):
    allow_reuse_address = False

    def __init__(self, path, token, handler, verify_peer):
        self.token, self.dispatch, self.verify_peer = token, handler, verify_peer
        self.sequence, self.frames = 0, 0
        super().__init__(str(path), ControlHandler)

    def handle_error(self, request, address):
        pass  # Never log a credential, input, response or exception message.


class ControlHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(25)
        try:
            if not self.server.verify_peer(*peer(self.request)):
                raise ControlFailure('authorization', 'denied')
            value = receive(self.request)
            if (type(value) is not dict or set(value) != {'schema_version', 'token', 'sequence', 'operation', 'value'}
                    or type(value['schema_version']) is not int or value['schema_version'] != 1
                    or type(value['sequence']) is not int or value['sequence'] != self.server.sequence + 1
                    or type(value['token']) is not str or not hmac.compare_digest(value['token'], self.server.token)
                    or self.server.frames >= 1024):
                raise ControlFailure('authorization', 'denied')
            self.server.sequence = value['sequence']
            self.server.frames += 1
            result = {'result': self.server.dispatch(value['operation'], value['value'])}
        except OperationsBlocked as failure:
            result = {'failure': {'kind': 'operations', 'stage': 'agent', 'reason': failure.code}}
        except Exception as failure:
            result = {'failure': dict(terminal_failure(failure), kind='control')}
        try:
            send(self.request, result)
        except Exception:
            pass


def check_fields(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ControlFailure('structured_input_validation', 'invalid_request')


class RemoteAudit:
    def __init__(self, client, kind):
        self.client, self.kind = client, kind

    def append(self, event):
        self.client.call('audit', {'kind': self.kind, 'event': event})


class RemoteOperations:
    def __init__(self, client):
        self.client, self.controller = client, self

    def handle(self, request):
        return self.client.call('operations', request)

    def budgets(self):
        return self.client.call('operations', {'operation': 'overview'})['budgets']
