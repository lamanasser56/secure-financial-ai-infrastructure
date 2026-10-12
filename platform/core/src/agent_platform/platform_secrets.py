"""`make secrets` (python -m agent_platform.platform_secrets): generate every platform secret once, on the owner's laptop, and create the Kubernetes Secrets.

Idempotent: if any platform Secret already exists, nothing is generated or changed (use --rotate deliberately).
Values are produced in memory and sent to `kubectl apply -f -` on stdin; nothing is written to disk or printed.
The owner types the operations-approval passphrase (only its scrypt hash is stored).
Who holds what:
  platform/postgres  owner password                 platform/gateway   master/salt keys, its DB URL
  platform/redactor  per-namespace client keys      platform/bootstrap role passwords, virtual keys + budgets
  apps/app           fixture issuer key, app keys, approver PRIVATE key, passphrase hash
  ops/ops-agent      approver PUBLIC key, ops keys  (the agent cannot sign approvals)
  agent-<name>/agent its own gateway key + redactor key (onboarded agents, platform/agents/*/agent.yaml); an agent that
                     declares data also gets its database URLs (web + read-only roles) and a session signing key
Financial Agent users (lama, sara, omar): random passwords, stored in the cluster only as argon2id hashes. The plaintext
passwords are written once to the owner's private state (financial-users.json, mode 0600) and never printed.

`--onboard` (run by `make up`, no passphrase): adds the keys of newly onboarded agents and applies the manifests'
budgets to the existing keys, without rotating anything that exists. Values are never printed.
"""
import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid

from agent_platform import onboarding
from agent_platform.identity_fixture import generate as generate_issuer
from agent_platform.ops.approval import generate_keypair
from agent_platform.programs.bootstrap import TENANTS

HOST = 'postgres.platform.svc.cluster.local:5432'
NAMES = [('platform', 'postgres'), ('platform', 'gateway'), ('platform', 'redactor'), ('platform', 'bootstrap'),
         ('apps', 'app'), ('ops', 'ops-agent')]
USERS = {'alpha': {'subject': 'platform-fixture-alpha', 'tenant': 'fixture-a'},
         'beta': {'subject': 'platform-fixture-beta', 'tenant': 'fixture-b'}}
FINANCE_USERS = (('lama', 'Lama'), ('sara', 'Sara'), ('omar', 'Omar'))
# argon2 on the owner's laptop: a venv with the Financial Agent's hash-locked set (created by `make up`).
TOOLS_PYTHON = onboarding.REPO / '.cache/finance-tools/bin/python'
HASH_SCRIPT = ('import json,sys; from argon2 import PasswordHasher; h=PasswordHasher(); '
               'print(json.dumps({u: h.hash(p) for u, p in json.load(sys.stdin).items()}))')


def argon2_hashes(passwords):
    """{username: password} -> {username: argon2id hash}; the passwords travel only over a pipe."""
    try:
        from argon2 import PasswordHasher
        hasher = PasswordHasher()
        return {u: hasher.hash(p) for u, p in passwords.items()}
    except ImportError:
        pass
    if not TOOLS_PYTHON.exists():
        raise SystemExit('argon2 is unavailable for the Financial Agent users (run make up, which creates .cache/finance-tools)')
    result = subprocess.run([str(TOOLS_PYTHON), '-I', '-c', HASH_SCRIPT], input=json.dumps(passwords), text=True,
                            capture_output=True, check=True)
    return json.loads(result.stdout)


def finance_config(hasher=argon2_hashes):
    passwords = {username: secrets.token_urlsafe(12) for username, _ in FINANCE_USERS}
    hashes = hasher(passwords)
    users = [{'id': str(uuid.uuid4()), 'username': u, 'display_name': d, 'password_hash': hashes[u]} for u, d in FINANCE_USERS]
    return {'web_password': secrets.token_hex(32), 'agent_password': secrets.token_hex(32), 'users': users}, passwords


def data_extras(manifest, finance):
    """An agent that declares data gets its two role URLs and a session signing key; others get nothing more."""
    if manifest['data'] == 'none':
        return {}
    url = lambda role, password: 'postgresql://' + role + ':' + password + '@' + HOST + '/' + manifest['data']['database']
    return {'web_db_url': url('finance_web', finance['web_password']), 'agent_db_url': url('finance_agent', finance['agent_password']),
            'session_key': secrets.token_hex(32)}


def write_users_file(path, passwords):
    """Owner-only file (0600) with the Financial Agent users' plaintext passwords; never printed."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump({'note': 'Financial Agent sign-in (port-forward 127.0.0.1:8081). Owner only; do not commit.',
                   'users': passwords}, handle, indent=1)


def budgets():
    """Gateway virtual keys and monthly budgets: platform keys + onboarded agents (sum = $10/month, owner decision)."""
    return onboarding.budgets(onboarding.load_all())


def agent_secret(name, gateway_key, redactor_key, extras=None):
    return secret('agent-' + name, 'agent', {'agent.json': json.dumps(dict({'gateway_key': gateway_key, 'redactor_key': redactor_key},
                                                                          **(extras or {})))})


def secret(namespace, name, data):
    return {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque', 'metadata': {'name': name, 'namespace': namespace,
            'labels': {'app.kubernetes.io/part-of': 'agent-platform'}},
            'data': {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}}


def generate(passphrase, *, hasher=argon2_hashes, users_out=None):
    h = lambda n=32: secrets.token_hex(n)
    owner, gateway_pw, app_pw = h(), h(), h()
    master, salt = 'sk-' + h(24), 'sk-' + h(24)
    manifests = onboarding.load_all()
    limits = onboarding.budgets(manifests)
    agents = onboarding.namespace_agents(manifests)
    virtual = {alias: 'sk-' + h(24) for alias in limits}
    redactor_keys = dict({'app': h(), 'ops': h()}, **{'agent-' + n: h() for n in agents})
    issuer_private, issuer_public = generate_issuer()
    approver_private, approver_public = generate_keypair()
    ops_api = h()
    salt_bytes = secrets.token_bytes(16)
    scrypt = {'salt': salt_bytes.hex(), 'hash': hashlib.scrypt(passphrase.encode(), salt=salt_bytes, n=2 ** 14, r=8, p=1).hex()}
    app = {'issuer_private_key': issuer_private, 'issuer_certificate': issuer_public, 'tenant_reference_key': h(),
           'tenant_directory': TENANTS, 'tenant_database_url': 'postgresql://portfolio_app:' + app_pw + '@' + HOST + '/portfolio_demo',
           'client_keys': {'financial': virtual['app-financial'], 'infrastructure': virtual['app-infrastructure']},
           'redactor_key': redactor_keys['app'], 'approver_private_key': approver_private,
           'operator_secret_scrypt': scrypt, 'ops_api_key': ops_api, 'users': USERS}
    ops = {'api_key': ops_api, 'approver_public_key': approver_public, 'gateway_key': virtual['ops-explain'],
           'redactor_key': redactor_keys['ops']}
    bootstrap = {'host': HOST, 'owner_password': owner, 'gateway_password': gateway_pw, 'app_password': app_pw,
                 'master_key': master, 'virtual_keys': [{'alias': a, 'key': k, 'max_budget': limits[a]} for a, k in virtual.items()]}
    if any(m['data'] != 'none' for m in manifests.values()):
        bootstrap['finance'], passwords = finance_config(hasher)
        if users_out is not None:
            users_out.update(passwords)
    return [secret('platform', 'postgres', {'owner_password': owner}),
            secret('platform', 'gateway', {'master_key': master, 'salt_key': salt,
                                           'database_url': 'postgresql://portfolio_gateway:' + gateway_pw + '@' + HOST + '/litellm'}),
            secret('platform', 'redactor', {'clients.json': json.dumps(redactor_keys)}),
            secret('platform', 'bootstrap', {'bootstrap.json': json.dumps(bootstrap)}),
            secret('apps', 'app', {'app.json': json.dumps(app)}),
            secret('ops', 'ops-agent', {'ops.json': json.dumps(ops)})] + [
            agent_secret(n, virtual['agent-' + n], redactor_keys['agent-' + n], data_extras(manifests[n], bootstrap.get('finance')))
            for n in agents]


def read_secret(kubectl, namespace, name, key):
    result = subprocess.run([kubectl, '-n', namespace, 'get', 'secret', name, '-o', 'json', '--ignore-not-found'],
                            capture_output=True, text=True, check=True)
    if not result.stdout.strip():
        return None
    return json.loads(base64.b64decode(json.loads(result.stdout)['data'][key]))


def onboard(kubectl, *, users_file=None, hasher=argon2_hashes):
    """Add keys for newly onboarded agents and apply the manifests' budgets; never rotates an existing key."""
    manifests = onboarding.load_all()
    limits = onboarding.budgets(manifests)
    bootstrap = read_secret(kubectl, 'platform', 'bootstrap', 'bootstrap.json')
    clients = read_secret(kubectl, 'platform', 'redactor', 'clients.json')
    if bootstrap is None or clients is None:
        raise SystemExit('secrets:platform_secrets_missing (run make secrets first)')
    virtual = {k['alias']: k for k in bootstrap['virtual_keys']}
    changed, added = False, []
    for alias, budget in limits.items():
        if alias not in virtual:
            virtual[alias] = {'alias': alias, 'key': 'sk-' + secrets.token_hex(24), 'max_budget': budget}
            changed = True
        elif virtual[alias]['max_budget'] != budget:
            virtual[alias]['max_budget'] = budget
            changed = True
    extra = sorted(set(virtual) - set(limits))
    if extra:
        raise SystemExit('secrets:keys_without_manifest ' + ','.join(extra))
    if any(m['data'] != 'none' for m in manifests.values()) and 'finance' not in bootstrap:
        bootstrap['finance'], passwords = finance_config(hasher)  # first agent with data: roles + users
        changed = True
        if users_file is not None:
            write_users_file(users_file, passwords)
    items = []
    for name in onboarding.namespace_agents(manifests):
        client = 'agent-' + name
        if client not in clients:
            clients[client] = secrets.token_hex(32)
            changed = True
        if read_secret(kubectl, client, 'agent', 'agent.json') is None:
            items.append(agent_secret(name, virtual[client]['key'], clients[client], data_extras(manifests[name], bootstrap.get('finance'))))
            added.append(client)
    if changed:
        bootstrap['virtual_keys'] = [virtual[a] for a in limits]
        items += [secret('platform', 'bootstrap', {'bootstrap.json': json.dumps(bootstrap)}),
                  secret('platform', 'redactor', {'clients.json': json.dumps(clients)})]
    if items:
        manifest = {'apiVersion': 'v1', 'kind': 'List', 'items': items}
        subprocess.run([kubectl, 'apply', '-f', '-'], input=json.dumps(manifest), text=True, check=True, capture_output=True)
    print(json.dumps({'result': 'ONBOARDED' if items else 'UNCHANGED', 'platform_keys_changed': changed,
                      'agent_secrets_created': added, 'values_printed': False}))
    return changed


def existing(kubectl):
    found = []
    for namespace, name in NAMES:
        result = subprocess.run([kubectl, '-n', namespace, 'get', 'secret', name, '-o', 'name', '--ignore-not-found'],
                                capture_output=True, text=True, check=True)
        if result.stdout.strip():
            found.append(namespace + '/' + name)
    return found


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--kubectl', default='kubectl')
    parser.add_argument('--rotate', action='store_true', help='replace existing Secrets (invalidates sessions and keys)')
    parser.add_argument('--onboard', action='store_true', help='add keys for onboarded agents (no rotation, no passphrase)')
    parser.add_argument('--users-file', type=Path, help="owner-only file for the Financial Agent users' passwords (0600)")
    args = parser.parse_args(argv)
    if args.onboard:
        onboard(args.kubectl, users_file=args.users_file)
        return
    present = existing(args.kubectl)
    if present and not args.rotate:
        print(json.dumps({'result': 'UNCHANGED', 'existing': present}))
        return
    if not sys.stdin.isatty():
        raise SystemExit('secrets:interactive_passphrase_required')
    passphrase = getpass.getpass('Operations approval passphrase (min 12 chars): ')
    if len(passphrase) < 12 or passphrase != getpass.getpass('Repeat: '):
        raise SystemExit('secrets:passphrase_rejected')
    passwords = {}
    manifest = {'apiVersion': 'v1', 'kind': 'List', 'items': generate(passphrase, users_out=passwords)}
    subprocess.run([args.kubectl, 'apply', '-f', '-'], input=json.dumps(manifest), text=True, check=True, capture_output=True)
    if passwords and args.users_file is not None:
        write_users_file(args.users_file, passwords)
    print(json.dumps({'result': 'CREATED', 'secrets': [n + '/' + s for n, s in NAMES], 'values_printed': False}))


if __name__ == '__main__':
    main(sys.argv[1:])
