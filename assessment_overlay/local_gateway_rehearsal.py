"""VM-only, internal-Docker rehearsal of main boundary -> LiteLLM -> fixed stub.

Takes the private output of render_live_bundle.py. Docker's --internal
network has no external route; the redactor response is a local synthetic
fixture, while the main GatewayBoundary and exact gateway/App images execute.
This does not consume the live SDP ledger or replace any deployed component.
"""

import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

import yaml


ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((Path(__file__).with_name('platform-images.lock.json')).read_text())


def run(*args, input=None, check=True):
    result = subprocess.run(['sudo', 'docker', *args], input=input,
                            capture_output=True, text=True, timeout=180)
    if check and result.returncode:
        raise RuntimeError('Docker operation failed: ' + args[0] + ' exit=' + str(result.returncode))
    return result


def get(docs, kind, namespace, prefix):
    found = [d for d in docs if d['kind'] == kind and
             d['metadata'].get('namespace', '') == namespace and
             (d['metadata']['name'] == prefix if kind == 'Secret'
              else d['metadata']['name'].startswith(prefix))]
    if len(found) != 1:
        raise ValueError('missing/duplicate local input: ' + kind + '/' + prefix)
    return found[0]


def private_file(directory, name, content):
    path = directory / name
    # Test-only synthetic credentials must be readable by the non-root image.
    path.write_text(content)
    path.chmod(0o644)
    return path


def main(bundle):
    bundle = Path(bundle).resolve()
    if bundle.is_relative_to(ROOT.resolve()):
        raise ValueError('private bundle cannot be inside repository')
    docs = [d for d in yaml.safe_load_all(bundle.read_text()) if d]
    lock = json.loads(bundle.with_suffix('.lock.json').read_text())
    if (lock['platform_commit'] != LOCK['source_commit']
            or lock['image_digests'] != LOCK['images']
            or hashlib.sha256(bundle.read_bytes()).hexdigest() != lock['bundle_sha256']):
        raise ValueError('private bundle qualification mismatch')
    registry = lock['source_registry']
    if (not registry.startswith('us-east1-docker.pkg.dev/')
            or not registry.endswith('/sdp-evaluation-images/')):
        raise ValueError('unreviewed source registry')
    image = lambda name: registry + LOCK['images'][name]
    for name in ('app', 'gateway', 'database'):
        if run('image', 'inspect', image(name), '--format', '{{.Id}}').stdout.strip() != \
                'sha256:' + LOCK['images'][name].split('@sha256:')[1]:
            raise ValueError('exact image missing: ' + name)
    secret = lambda ns, name, key: base64.b64decode(get(docs, 'Secret', ns, name)['data'][key]).decode()
    bootstrap = json.loads(secret('platform', 'bootstrap', 'bootstrap.json'))
    boundary = json.loads(secret('platform', 'gateway-boundary', 'boundary.json'))
    gateway_secret = get(docs, 'Secret', 'platform', 'gateway')['data']
    master = base64.b64decode(gateway_secret['master_key']).decode()
    salt = base64.b64decode(gateway_secret['salt_key']).decode()
    database_url = base64.b64decode(gateway_secret['database_url']).decode()
    tag = secrets.token_hex(4)
    network = 'assessment-private-' + tag
    pg, stub, gateway = [network + '-' + name for name in ('pg', 'stub', 'gateway')]
    tmp = bundle.parent / ('local-gateway-' + tag)
    tmp.mkdir(mode=0o700)
    for name in ('config', 'programs', 'sql', 'bootstrap', 'stub', 'boundary'):
        (tmp / name).mkdir(mode=0o755)
    cfg = get(docs, 'ConfigMap', 'platform', 'gateway-config-')['data']
    if 'vertex_ai/' in cfg['litellm.yaml']:
        raise ValueError('external route in local rehearsal')
    for name, content in cfg.items():
        private_file(tmp / 'config', name, content)
    programs = get(docs, 'ConfigMap', 'platform', 'platform-programs-')['data']
    private_file(tmp / 'programs', 'gateway_entry.py', programs['gateway_entry.py'])
    for name, content in get(docs, 'ConfigMap', 'platform', 'database-sql-')['data'].items():
        private_file(tmp / 'sql', name, content)
    private_file(tmp / 'bootstrap', 'bootstrap.json', json.dumps(bootstrap))
    private_file(tmp / 'stub', 'provider_stub.py',
                 get(docs, 'ConfigMap', 'assess-probes', 'provider-stub-code')['data']['provider_stub.py'])
    private_file(tmp / 'boundary', 'boundary.json', json.dumps(boundary))
    created_network = False
    receipt = {'platform_commit': LOCK['source_commit'], 'bundle_sha256': lock['bundle_sha256'],
               'network_internal': False, 'external_llm_calls': 0, 'gateway_path': 'NOT_RUN'}
    try:
        run('network', 'create', '--internal', network)
        created_network = True
        net_info = json.loads(run('network', 'inspect', network).stdout)[0]
        if net_info['Internal'] is not True:
            raise RuntimeError('Docker network is not internal')
        receipt['network_internal'] = True
        run('run', '-d', '--rm', '--name', pg, '--network', network,
            '--network-alias', 'postgres.platform.svc.cluster.local',
            '--tmpfs', '/var/lib/postgresql/data:uid=70,gid=70,mode=0700',
            '-e', 'POSTGRES_PASSWORD=' + bootstrap['owner_password'], image('database'))
        for _ in range(80):
            if run('exec', pg, 'pg_isready', '-U', 'postgres', check=False).returncode == 0:
                break
            time.sleep(.5)
        else:
            raise RuntimeError('exact database image did not start')
        mounts = ['-v', str(tmp / 'bootstrap') + ':/secrets/bootstrap:ro',
                  '-v', str(tmp / 'sql') + ':/sql:ro']
        run('run', '--rm', '--network', network, '--read-only', '--tmpfs', '/tmp:mode=1777',
            *mounts, '--entrypoint', '/usr/local/bin/python3.12', image('app'),
            '-B', '-m', 'agent_platform.programs.bootstrap', 'database')
        run('run', '-d', '--rm', '--name', stub, '--network', network,
            '--network-alias', 'provider-stub.assess-probes.svc.cluster.local',
            '--read-only', '--tmpfs', '/tmp:mode=1777',
            '-v', str(tmp / 'stub') + ':/assessment:ro',
            '--entrypoint', '/usr/local/bin/python3.12', image('app'),
            '-u', '/assessment/provider_stub.py')
        run('run', '-d', '--rm', '--name', gateway, '--network', network,
            '--network-alias', 'gateway-provider.platform.svc.cluster.local',
            '--read-only', '--tmpfs', '/tmp:uid=65532,gid=65532,mode=0700',
            '-v', str(tmp / 'config') + ':/config:ro',
            '-v', str(tmp / 'programs') + ':/programs:ro',
            '-e', 'DATABASE_URL=' + database_url,
            '-e', 'LITELLM_MASTER_KEY=' + master,
            '-e', 'LITELLM_SALT_KEY=' + salt,
            '-e', 'PORTFOLIO_PROJECT_ID=sfai-assess-20261022-635651',
            '--entrypoint', '/usr/local/bin/python3.12', image('gateway'),
            '/programs/gateway_entry.py')
        probe = ('import urllib.request;'
            "r=urllib.request.urlopen('http://127.0.0.1:4001/health/liveliness',timeout=2);"
            'assert r.status==200')
        for _ in range(120):
            if run('exec', gateway, '/usr/local/bin/python3.12', '-c', probe,
                   check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('exact LiteLLM gateway did not become healthy')
        run('run', '--rm', '--network', network, '--read-only', '--tmpfs', '/tmp:mode=1777',
            *mounts, '--entrypoint', '/usr/local/bin/python3.12', image('app'),
            '-B', '-m', 'agent_platform.programs.bootstrap', 'keys')
        code = '''import json
from pathlib import Path
from types import SimpleNamespace
from agent_platform.gateway_boundary import GatewayBoundary
config=json.loads(Path('/assessment/boundary.json').read_text())
class SyntheticRedactor:
 def redact(self, text):
  return SimpleNamespace(text='[REDACTED]',categories=['PHONE_NUMBER'])
b=GatewayBoundary(config['clients'],SyntheticRedactor())
body={'model':'secure-financial-chat','messages':[{'role':'user','content':'Call +1 202-555-0101'}],
 'temperature':0,'max_tokens':64,'stream':False,'response_format':{'type':'json_object'}}
result,headers=b.handle('/v1/chat/completions','Bearer '+config['clients']['app-financial']['external_key'],body)
assert result['choices'][0]['message']['content']=='{"action":"answer","text":"Synthetic response."}'
print('GATEWAY_STUB_D02_PASS')'''
        request = run('run', '--rm', '--network', network, '--read-only',
            '--tmpfs', '/tmp:mode=1777', '-v', str(tmp / 'boundary') + ':/assessment:ro',
            '--entrypoint', '/usr/local/bin/python3.12', image('app'), '-c', code,
            check=False)
        if request.returncode:
            raise RuntimeError('gateway boundary rehearsal failed: ' +
                               request.stderr[-500:].replace(master, '[REDACTED]'))
        response = request.stdout
        if 'GATEWAY_STUB_D02_PASS' not in response:
            raise RuntimeError('main gateway boundary did not reach fixed stub')
        stats = json.loads(run('exec', stub, '/usr/local/bin/python3.12', '-c',
            "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/stats').read().decode())").stdout)
        if stats != {'requests': 1, 'raw_canary_seen': False}:
            raise RuntimeError('stub dispatch counter or raw canary assertion failed')
        receipt['gateway_path'] = 'PASS'
        receipt['stub_requests'] = 1
        receipt['raw_canary_seen'] = False
        return receipt
    finally:
        for name in (gateway, stub, pg):
            run('rm', '-f', name, check=False)
        if created_network:
            run('network', 'rm', network, check=False)
        if tmp.resolve().is_relative_to(bundle.parent.resolve()):
            shutil.rmtree(tmp)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: local_gateway_rehearsal.py PRIVATE_BUNDLE')
    print(json.dumps(main(sys.argv[1]), sort_keys=True))
