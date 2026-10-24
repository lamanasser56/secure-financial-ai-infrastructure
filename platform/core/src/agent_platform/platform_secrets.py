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
                     declares data gets per-worker broker/worker credentials and a public capability verification key only.
  apps/financial-frontdoor holds DB and session/capability signing keys; platform/gateway-boundary holds private
  upstream keys; ops/ops-executor alone receives mutation authority plus durable replay storage.
Financial Agent users (lama, sara, omar): random passwords, stored in the cluster only as argon2id hashes. The plaintext
passwords are written once to the owner's private state (financial-users.json, mode 0600) and never printed.

`--onboard` (run by `make up`, no passphrase): adds the keys of newly onboarded agents and applies the manifests'
budgets to the existing keys, without rotating anything that exists. Values are never printed.

`--retire-agent NAME` (owner, once per retired agent, after its manifest is removed): drops that agent's entries from
Secrets platform/bootstrap and platform/redactor. Nothing else changes; running it again changes nothing.
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
         ('apps', 'app'), ('ops', 'ops-agent'), ('platform', 'gateway-boundary'),
         ('apps', 'financial-frontdoor'), ('ops', 'ops-executor')]
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


def finance_config(hasher=argon2_hashes, user_directory=None):
    if user_directory is not None:
        names = {u for u, _ in FINANCE_USERS}
        if (type(user_directory) is not dict or set(user_directory) != names
                or any(type(v) is not str or str(uuid.UUID(v)) != v for v in user_directory.values())
                or len(set(user_directory.values())) != len(names)):
            raise ValueError('reviewed existing user directory must contain distinct canonical UUIDs for the configured users')
        users = [{'id': user_directory[u], 'username': u, 'display_name': d, 'password_hash': None} for u,d in FINANCE_USERS]
        return {'broker_web_password': secrets.token_hex(32), 'broker_read_password': secrets.token_hex(32),
                'users': users, 'preserve_existing_users': True}, {}

    passwords = {username: secrets.token_urlsafe(12) for username, _ in FINANCE_USERS}
    hashes = hasher(passwords)
    users = [{'id': str(uuid.uuid4()), 'username': u, 'display_name': d, 'password_hash': hashes[u]} for u, d in FINANCE_USERS]
    return {'broker_web_password': secrets.token_hex(32), 'broker_read_password': secrets.token_hex(32), 'users': users}, passwords


def data_extras(manifest, context):
    """No onboarded agent receives a database password, user-auth hash access or session/capability signing key."""
    if manifest['data'] == 'none':
        return {}
    name = manifest['agent']
    return {'agent_name': name, 'broker_key': context['broker_clients'][name],
            'worker_key': context['worker_keys'][name], 'capability_public_key': context['capability_public_key']}


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


def generate(passphrase, *, hasher=argon2_hashes, users_out=None, user_directory=None):
    h = lambda n=32: secrets.token_hex(n)
    owner, gateway_pw, app_pw = h(), h(), h()
    master, salt = 'sk-' + h(24), 'sk-' + h(24)
    manifests = onboarding.load_all()
    limits = onboarding.budgets(manifests)
    agents = onboarding.namespace_agents(manifests)
    virtual = {alias: 'sk-' + h(24) for alias in limits}
    external = {alias: 'gw-' + h(24) for alias in limits}
    redactor_keys = dict({'app': h(), 'ops': h(), 'gateway-boundary': h()}, **{'agent-' + n: h() for n in agents})
    issuer_private, issuer_public = generate_issuer()
    approver_private, approver_public = generate_keypair()
    cap_private, cap_public = generate_keypair()
    data_agents = [n for n in agents if manifests[n]['data'] != 'none']
    context = {'broker_clients': {n: h() for n in data_agents}, 'worker_keys': {n: h() for n in data_agents},
               'capability_public_key': cap_public}
    per_user = {}
    ops_api, executor_api = h(), h()
    salt_bytes = secrets.token_bytes(16)
    scrypt = {'salt': salt_bytes.hex(), 'hash': hashlib.scrypt(passphrase.encode(), salt=salt_bytes, n=2 ** 14, r=8, p=1).hex()}
    app = {'issuer_private_key': issuer_private, 'issuer_certificate': issuer_public, 'tenant_reference_key': h(),
           'tenant_directory': TENANTS, 'tenant_database_url': 'postgresql://portfolio_app:' + app_pw + '@' + HOST + '/portfolio_demo',
           'client_keys': {'financial': external['app-financial'], 'infrastructure': external['app-infrastructure']},
           'redactor_key': redactor_keys['app'], 'approver_private_key': approver_private,
           'operator_secret_scrypt': scrypt, 'ops_api_key': ops_api, 'users': USERS}
    ops = {'api_key': ops_api, 'approver_public_key': approver_public, 'gateway_key': external['ops-explain'],
           'redactor_key': redactor_keys['ops'], 'executor_key': executor_api}
    bootstrap = {'host': HOST, 'owner_password': owner, 'gateway_password': gateway_pw, 'app_password': app_pw,
                 'master_key': master, 'boundary_contract': 2, 'virtual_keys': [{'alias': 'boundary-' + a, 'key': k, 'max_budget': limits[a]} for a, k in virtual.items()]}
    if any(m['data'] != 'none' for m in manifests.values()):
        bootstrap['finance'], passwords = finance_config(hasher, user_directory=user_directory)
        # Slots are opaque deployment identities. Each receives only its own broker/worker credential.
        for slot, user in zip(onboarding.USER_SLOTS, bootstrap['finance']['users']):
            principal = 'financial-' + slot
            per_user[slot] = {'agent_name': principal, 'user_id': user['id'], 'broker_key': h(), 'worker_key': h(),
                              'capability_public_key': cap_public}
        context['broker_clients'] = {value['agent_name']: value['broker_key'] for value in per_user.values()}
        context['worker_keys'] = {value['agent_name']: value['worker_key'] for value in per_user.values()}

        if users_out is not None:
            users_out.update(passwords)
    frontdoor = dict(context, capability_private_key=cap_private, agent_name='financial',
                     session_key=h(),
                     user_bindings={value['agent_name']: value['user_id'] for value in per_user.values()},
                     routes={value['user_id']: {'agent': value['agent_name'], 'key': value['worker_key'],
                             'url': 'http://agent-' + slot + '.agent-financial.svc.cluster.local:8081/ask'}
                             for slot, value in per_user.items()},
                     web_db_url='postgresql://finance_frontdoor:' + bootstrap['finance']['broker_web_password'] + '@' + HOST + '/finance',
                     read_db_url='postgresql://finance_data_broker:' + bootstrap['finance']['broker_read_password'] + '@' + HOST + '/finance')
    return [secret('platform', 'gateway-boundary', {'boundary.json': json.dumps({
                'clients': {a: {'external_key': external[a], 'upstream_key': virtual[a]} for a in limits},
                'redactor_key': redactor_keys['gateway-boundary']})}),
            secret('apps', 'financial-frontdoor', {'frontdoor.json': json.dumps(frontdoor)}),
            secret('ops', 'ops-executor', {'executor.json': json.dumps({'api_key': executor_api, 'approver_public_key': approver_public})}),
            secret('platform', 'postgres', {'owner_password': owner}),
            secret('platform', 'gateway', {'master_key': master, 'salt_key': salt,
                                           'database_url': 'postgresql://portfolio_gateway:' + gateway_pw + '@' + HOST + '/litellm'}),
            secret('platform', 'redactor', {'clients.json': json.dumps(redactor_keys)}),
            secret('platform', 'bootstrap', {'bootstrap.json': json.dumps(bootstrap)}),
            secret('apps', 'app', {'app.json': json.dumps(app)}),
            secret('ops', 'ops-agent', {'ops.json': json.dumps(ops)})] + [agent_secret(n, external['agent-' + n], redactor_keys['agent-' + n]) for n in agents if manifests[n]['data'] == 'none'] + [
            secret('agent-financial', 'agent-' + slot, {'agent.json': json.dumps(dict(value,
                   gateway_key=external['agent-financial'], redactor_key=redactor_keys['agent-financial']))})
            for slot, value in per_user.items()]



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
    if bootstrap.get('boundary_contract') != 2:
        raise SystemExit('secrets:reviewed_boundary_migration_required')
    boundary = read_secret(kubectl, 'platform', 'gateway-boundary', 'boundary.json')
    frontdoor = read_secret(kubectl, 'apps', 'financial-frontdoor', 'frontdoor.json')
    if boundary is None or frontdoor is None:
        raise SystemExit('secrets:trusted_boundary_secrets_missing')
    virtual = {k['alias'].removeprefix('boundary-'): k for k in bootstrap['virtual_keys']}
    changed, added = False, []
    for alias, budget in limits.items():
        if alias not in virtual:
            virtual[alias] = {'alias': 'boundary-' + alias, 'key': 'sk-' + secrets.token_hex(24), 'max_budget': budget}
            boundary['clients'][alias] = {'external_key': 'gw-' + secrets.token_hex(24), 'upstream_key': virtual[alias]['key']}
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
        if manifests[name]['data'] != 'none':
            if name != 'financial' or any(read_secret(kubectl, client, 'agent-' + slot, 'agent.json') is None for slot in onboarding.USER_SLOTS):
                raise SystemExit('secrets:reviewed_per_user_frontdoor_provisioning_required')
            continue
        if read_secret(kubectl, client, 'agent', 'agent.json') is None:
            if manifests[name]['data'] != 'none' and name not in frontdoor['broker_clients']:
                frontdoor['broker_clients'][name] = secrets.token_hex(32)
                frontdoor['worker_keys'][name] = secrets.token_hex(32)
            items.append(agent_secret(name, boundary['clients'][client]['external_key'], clients[client], data_extras(manifests[name], frontdoor)))
            added.append(client)
    if changed:
        bootstrap['virtual_keys'] = [virtual[a] for a in limits]
        items += [secret('platform', 'bootstrap', {'bootstrap.json': json.dumps(bootstrap)}),
                  secret('platform', 'redactor', {'clients.json': json.dumps(clients)}),
                  secret('platform', 'gateway-boundary', {'boundary.json': json.dumps(boundary)}),
                  secret('apps', 'financial-frontdoor', {'frontdoor.json': json.dumps(frontdoor)})]
    if items:
        manifest = {'apiVersion': 'v1', 'kind': 'List', 'items': items}
        subprocess.run([kubectl, 'apply', '-f', '-'], input=json.dumps(manifest), text=True, check=True, capture_output=True)
    print(json.dumps({'result': 'ONBOARDED' if items else 'UNCHANGED', 'platform_keys_changed': changed,
                      'agent_secrets_created': added, 'values_printed': False}))
    return changed


def retire(kubectl, name):
    """Remove one retired agent's entries from Secrets platform/bootstrap (gateway virtual key) and platform/redactor
    (client key). Nothing else is rotated or removed; idempotent; only alias names are printed, never values."""
    if not onboarding.NAME.fullmatch(name) or name in onboarding.RESERVED:
        raise SystemExit('secrets:retire_name_rejected')
    if name in onboarding.names():
        raise SystemExit('secrets:agent_still_declared (remove its manifest first)')
    alias = 'agent-' + name
    bootstrap = read_secret(kubectl, 'platform', 'bootstrap', 'bootstrap.json')
    clients = read_secret(kubectl, 'platform', 'redactor', 'clients.json')
    if bootstrap is None or clients is None:
        raise SystemExit('secrets:platform_secrets_missing')
    if bootstrap.get('boundary_contract') != 2:
        raise SystemExit('secrets:reviewed_boundary_migration_required')
    boundary = read_secret(kubectl, 'platform', 'gateway-boundary', 'boundary.json')
    frontdoor = read_secret(kubectl, 'apps', 'financial-frontdoor', 'frontdoor.json')
    if not boundary or not frontdoor:
        raise SystemExit('secrets:trusted_boundary_secrets_missing')
    if frontdoor['agent_name'] == name:
        raise SystemExit('secrets:retire_trusted_frontdoor_route_first')
    keys = [k for k in bootstrap['virtual_keys'] if k['alias'] != 'boundary-' + alias]
    removed = {'upstream_key': len(keys) != len(bootstrap['virtual_keys']), 'external_key': alias in boundary['clients'],
               'redactor_client_key': alias in clients}
    bootstrap['virtual_keys'] = keys
    boundary['clients'].pop(alias, None)
    clients.pop(alias, None)
    frontdoor['broker_clients'].pop(name, None)
    frontdoor['worker_keys'].pop(name, None)
    if any(removed.values()):
        items = [secret('platform', 'bootstrap', {'bootstrap.json': json.dumps(bootstrap)}),
                 secret('platform', 'gateway-boundary', {'boundary.json': json.dumps(boundary)}),
                 secret('platform', 'redactor', {'clients.json': json.dumps(clients)}),
                 secret('apps', 'financial-frontdoor', {'frontdoor.json': json.dumps(frontdoor)})]
        subprocess.run([kubectl, 'apply', '-f', '-'], input=json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': items}),
                       text=True, check=True, capture_output=True)
    print(json.dumps({'result': 'RETIRED' if any(removed.values()) else 'UNCHANGED', 'alias': alias, 'removed': removed,
                      'values_printed': False}))
    return removed


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
    parser.add_argument('--finance-user-directory', type=Path, help='reviewed existing username-to-UUID map; preserves DB IDs/password hashes; no automatic original DB access')
    parser.add_argument('--rotate', action='store_true', help='replace existing Secrets (invalidates sessions and keys)')
    parser.add_argument('--onboard', action='store_true', help='add keys for onboarded agents (no rotation, no passphrase)')
    parser.add_argument('--retire-agent', metavar='NAME', help="remove a retired agent's gateway and redactor key entries")
    parser.add_argument('--users-file', type=Path, help="owner-only file for the Financial Agent users' passwords (0600)")
    args = parser.parse_args(argv)
    if args.onboard:
        onboard(args.kubectl, users_file=args.users_file)
        return
    if args.retire_agent:
        retire(args.kubectl, args.retire_agent)
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
    manifest = {'apiVersion': 'v1', 'kind': 'List', 'items': generate(passphrase, users_out=passwords, user_directory=json.loads(args.finance_user_directory.read_text()) if args.finance_user_directory else None)}
    subprocess.run([args.kubectl, 'apply', '-f', '-'], input=json.dumps(manifest), text=True, check=True, capture_output=True)
    if passwords and args.users_file is not None:
        write_users_file(args.users_file, passwords)
    print(json.dumps({'result': 'CREATED', 'secrets': [n + '/' + s for n, s in NAMES], 'values_printed': False}))


if __name__ == '__main__':
    main(sys.argv[1:])
