"""Trusted local registrations, fixture identity and fixed read-only visibility."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

from runtime.agents.identity import SubjectGrant, TrustedJWTIdentity
from runtime.agents.operations import (ACTIONS, CacheTarget, OperationsBlocked, StackTarget,
    cache_inventory, private_directory, process_identity)

ROOT = Path(__file__).resolve().parents[2]


def registered_targets(config, tenant):
    """Private operator-owned registry, accepted at startup only.

    Browser/model cannot create targets. Cache registration explicitly declares
    public disposable content and pins the reviewed full inode/byte inventory.
    Process registration records identity at creation, never discovers by port.
    """
    if set(config) != {'schema_version', 'targets'} or config['schema_version'] != 1 or type(config['targets']) is not dict or len(config['targets']) > 8:
        raise OperationsBlocked('INVALID_REQUEST')
    targets = {}
    for identifier, row in config['targets'].items():
        if row['kind'] == 'cache':
            if set(row) != {'kind', 'path', 'manifest', 'content_class', 'mutable'} or row['content_class'] != 'public_disposable' or type(row['mutable']) is not bool:
                raise OperationsBlocked('INVALID_REQUEST')
            path = private_directory(row['path'])
            manifest = tuple(tuple(x) for x in row['manifest'])
            if cache_inventory(path) != manifest:
                raise OperationsBlocked('EVIDENCE_CHANGED')
            targets[identifier] = CacheTarget(tenant, path, manifest, row['mutable'])
        elif row['kind'] == 'stack':
            if set(row) != {'kind', 'supervisor', 'members', 'mutable', 'resource_scope'} or row['resource_scope'] != 'process_only' or type(row['mutable']) is not bool or not 1 <= len(row['members']) <= 4:
                raise OperationsBlocked('INVALID_REQUEST')
            for record in [row['supervisor'], *row['members']]:
                if set(record) != {'pid', 'start_ticks', 'uid', 'command_integrity'} or record['uid'] != os.getuid() or type(record['pid']) is not int or record['pid'] <= 1 or record['pid'] == os.getpid():
                    raise OperationsBlocked('OWNER_CHANGED')
                current = process_identity(record['pid'])
                if current is not None and current != record:
                    raise OperationsBlocked('OWNER_CHANGED')
            targets[identifier] = StackTarget(tenant, row['supervisor'], tuple(row['members']), row['mutable'])
        else:
            raise OperationsBlocked('INVALID_REQUEST')
    return targets


def fixture_identity():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from google.auth import crypt, jwt
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    now = int(time.time())
    token = jwt.encode(crypt.RSASigner.from_string(pem, key_id='operations-fixture'),
        {'iss': 'https://fixture-issuer.invalid', 'aud': 'local-operations',
         'sub': 'local-operations-operator', 'iat': now, 'exp': now + 1800}).decode()
    identity = TrustedJWTIdentity('infrastructure', issuer='https://fixture-issuer.invalid',
        audience='local-operations', certificates={'operations-fixture': public},
        snapshot_expires_at=now + 1800,
        subjects={'local-operations-operator': SubjectGrant('operations-fixture', frozenset({'infrastructure'}))},
        tenant_reference_key=secrets.token_bytes(32))
    # Fixed server grant, never scopes asserted by the token, browser or model.
    identity._actions = frozenset(ACTIONS.values())
    authorization = 'Bearer ' + token
    tenant = identity.resolve(identity.authenticate(authorization)).tenant_ref
    return identity, authorization, tenant


class ProcVisibility:
    def __init__(self):
        self.script = ROOT / 'scripts/inspect-operations-active-path.py'
        self.integrity = hashlib.sha256(self.script.read_bytes()).hexdigest()

    def __call__(self, path):
        if hashlib.sha256(self.script.read_bytes()).hexdigest() != self.integrity:
            raise OperationsBlocked('EVIDENCE_CHANGED')
        # Existing native operator sudo, read-only helper only. No shell/env/DSN.
        try:
            result = subprocess.run(['sudo', '-n', '/usr/bin/python3', '-I', '-B',
                str(self.script), '--target', str(path)], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=3)
            if result.returncode != 0 or len(result.stdout) > 128:
                raise ValueError
            value = json.loads(result.stdout)
            if set(value) != {'active', 'complete'} or value['complete'] is not True or type(value['active']) is not bool:
                raise ValueError
            return value['active']
        except OperationsBlocked:
            raise
        except Exception:
            raise OperationsBlocked('INCOMPLETE_VISIBILITY') from None


def register_monitor(state, tenant):
    state = private_directory(state)
    owner = json.loads((state / 'launcher-owner.json').read_text())
    supervisor = process_identity(owner['pid'])
    if supervisor is None or supervisor['start_ticks'] != owner['start_ticks']:
        raise OperationsBlocked('OWNER_CHANGED')
    records = json.loads((state / 'application/processes.json').read_text())
    members = []
    for record in records:
        current = process_identity(record['pid'])
        if current is None or current['start_ticks'] != record['start_ticks'] or current['uid'] != os.getuid():
            raise OperationsBlocked('OWNER_CHANGED')
        members.append(current)
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            if any(arg.endswith(b'/scripts/serve-integrated-agents.py') for arg in args) and str(state / 'application').encode() in args:
                current = process_identity(int(proc.name))
                if current is not None and current['uid'] == os.getuid():
                    members.append(current)
        except FileNotFoundError:
            continue
    if not 1 <= len(members) <= 4:
        raise OperationsBlocked('INVALID_REQUEST')
    return StackTarget(tenant, supervisor, tuple(members), False,
                       state / 'private-runtime.log', 'integrated_docker_monitor_only')


def sandbox_targets(state, tenant, *, stubborn=False):
    """Actual disposable service/cache, independently owned by this sandbox."""
    state = private_directory(state)
    supervisor = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(.2)'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    owner = process_identity(supervisor.pid)
    supervisor.wait(timeout=2)
    program = ('import socket,time,signal;'
        + ('signal.signal(signal.SIGTERM,signal.SIG_IGN);' if stubborn else '')
        + 's=socket.socket();s.bind(("127.0.0.1",0));s.listen();print("ready",flush=True);time.sleep(1800)')
    child = subprocess.Popen([sys.executable, '-u', '-c', program],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        start_new_session=True, text=True)
    assert child.stdout.readline().strip() == 'ready'
    child.stdout.close()
    member = process_identity(child.pid)
    cache = state / 'disposable-cache'; cache.mkdir(mode=0o700)
    (cache / 'public-1.cache').write_bytes(b'public disposable test content\n' * 4096)
    (cache / 'public-1.cache').chmod(0o600)
    targets = {'sandbox-demo': StackTarget(tenant, owner, (member,), True),
        'sandbox-cache': CacheTarget(tenant, cache, cache_inventory(cache), True)}
    return targets, child


def stop_sandbox_child(child, member):
    """Operator server shutdown owns only the child it created, never a port."""
    current = process_identity(child.pid)
    if current is not None:
        if current != member:
            raise OperationsBlocked('OWNER_CHANGED')
        fd = os.pidfd_open(child.pid)
        try:
            signal.pidfd_send_signal(fd, signal.SIGTERM)
            child.wait(timeout=3)
        finally:
            os.close(fd)
    else:
        child.wait(timeout=3)
