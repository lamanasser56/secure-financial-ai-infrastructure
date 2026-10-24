"""Offline startup probes for locally built images. Run on the worker VM with Docker.

All containers have network=none. Synthetic config is used only to start the
Financial and Guide HTTP processes; only loopback health requests are sent.
"""

import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'assessment_overlay'
PROGRAMS = ROOT / 'platform/core/src/agent_platform/programs'
IMAGES = {
    'app': 'local/agent-platform-app:assessment-41ff',
    'ops': 'local/agent-platform-ops:assessment-41ff',
    'financial': 'local/agent-financial:assessment-41ff',
    'guide': 'local/platform-guide:assessment-41ff',
    'redactor': 'local/sdp-redactor:assessment-41ff',
}


def docker(*args):
    return subprocess.run(['docker', *args], check=True, capture_output=True, text=True).stdout.strip()


def one_shot(image, command, *, mounts=(), env=(), tmpfs=()):
    args = ['run', '--rm', '--network', 'none', '--read-only']
    for directory in tmpfs:
        args.extend(['--tmpfs', directory])
    for source, target in mounts:
        args.extend(['--mount', f'type=bind,src={source},dst={target},readonly'])
    for name, value in env:
        args.extend(['-e', f'{name}={value}'])
    return docker(*args, '--entrypoint', command[0], image, *command[1:])


def server_health(image, config, command, port):
    name = 'assessment-preflight-' + secrets.token_hex(4)
    with tempfile.TemporaryDirectory(prefix='assessment-synthetic-') as temporary:
        directory = Path(temporary)
        (directory / 'agent.json').write_text(json.dumps(config))
        os.chmod(directory, 0o755)
        os.chmod(directory / 'agent.json', 0o644)
        docker('run', '--rm', '-d', '--name', name, '--network', 'none', '--read-only',
               '--tmpfs', '/tmp:uid=65532,gid=65532,mode=0700', '--mount',
               f'type=bind,src={directory},dst=/secrets/agent,readonly', image)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                probe = subprocess.run(['docker', 'exec', name, *command, port],
                                       capture_output=True, text=True)
                if probe.returncode == 0 and 'HEALTH_OK' in probe.stdout:
                    return
                time.sleep(0.25)
            raise AssertionError('container health startup failed: ' + image)
        finally:
            docker('rm', '-f', name)


def main():
    app_code = (
        'import agent_platform.app, http.client, threading; '
        'from runtime.agents.web import DemoServer; '
        "s=DemoServer(('127.0.0.1',0),agents={},composition='platform_live'); "
        't=threading.Thread(target=s.serve_forever,daemon=True); t.start(); '
        "c=http.client.HTTPConnection('127.0.0.1',s.server_port,timeout=3); "
        "c.request('GET','/'); r=c.getresponse(); assert r.status==200 and r.read(); "
        "c.close(); s.shutdown(); s.server_close(); t.join(3); print('APP_STARTUP_OK')"
    )
    assert 'APP_STARTUP_OK' in one_shot(IMAGES['app'],
        ['/usr/local/bin/python3.12', '-c', app_code])

    assert 'CONTAINER OPS PASS' in one_shot(IMAGES['ops'],
        ['/usr/local/bin/python3.12', '-B', '/assessment/container_ops_probe.py'],
        mounts=[(OVERLAY, '/assessment')],
        tmpfs=['/assessment-state:uid=65532,gid=65532,mode=0700'])

    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.PEM,
                                           serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    financial = {'gateway_key': 'g' * 64, 'redactor_key': 'r' * 64,
                 'agent_name': 'financial', 'broker_key': 'b' * 64,
                 'worker_key': 'w' * 64, 'capability_public_key': public,
                 'user_id': '00000000-0000-4000-8000-000000000001'}
    py_health = [
        '/usr/local/bin/python3.12', '-c',
        "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:'+sys.argv[1]+'/healthz',timeout=2); "
        "assert r.status==200; print('HEALTH_OK')",
    ]
    server_health(IMAGES['financial'], financial, py_health, '8081')

    guide = {'gateway_key': 'g' * 64, 'redactor_key': 'r' * 64}
    node_health = ['/nodejs/bin/node', '-e',
                   "fetch('http://127.0.0.1:'+process.argv[1]+'/healthz').then(r=>{if(r.status!==200)"
                   "process.exit(1);console.log('HEALTH_OK')}).catch(()=>process.exit(1))"]
    server_health(IMAGES['guide'], guide, node_health, '8082')

    guard_hash = hashlib.sha256((OVERLAY / 'sdp_guard.py').read_bytes()).hexdigest()
    assert 'CONTAINER REDACTOR PASS' in one_shot(IMAGES['redactor'],
        ['/usr/local/bin/python3.12', '-B', '/assessment/container_redactor_probe.py'],
        mounts=[(PROGRAMS, '/programs'), (OVERLAY, '/assessment')],
        env=[('ASSESSMENT_RUN_ID', 'assess-0000000000000001'),
             ('ASSESSMENT_GUARD_SHA256', guard_hash)],
        tmpfs=['/assessment-state:uid=65532,gid=65532,mode=0700'])

    print(json.dumps({'main': '41ffbf260a446b5db2292356a8ea23219e58a524',
                      'checks': {name: 'PASS' for name in IMAGES},
                      'images': {name: docker('image', 'inspect', image, '--format', '{{.Id}}')
                                 for name, image in IMAGES.items()}}, sort_keys=True))


if __name__ == '__main__':
    main()
