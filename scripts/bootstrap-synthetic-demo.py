#!/usr/bin/env python3
"""Prepared operator-only schema/client provisioning, no model request.

Two fixed phases run in distinct once-only bootstrap Jobs. Privileged credentials
and output stay private and must be removed before admitting the catalog Job.
The image signature does not cover this separately hashed program.
"""
import json
import os
from pathlib import Path
import secrets
import sys
import time
import urllib.request

TENANTS = {'fixture-a': '11111111-1111-4111-8111-111111111111',
           'fixture-b': '22222222-2222-4222-8222-222222222222'}
GATEWAY = 'http://gateway.google-agent-demo.svc.cluster.local:4000'


def issue_clients(config, state):
    """One revoked probe plus four distinct clients; failed calls consume slots.

    No retries, refresh or model call. The once-only phase marker is owned by
    run(); native scope approval controls whether another phase may be started.
    """
    counts = {'client_issuance_attempts': 0, 'client_revocation_attempts': 0}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def call(path, data, counter):
        cap = 5 if counter == 'client_issuance_attempts' else 1
        if counts[counter] >= cap or time.time() >= config['expires_at']:
            raise ValueError('bootstrap:client_budget')
        counts[counter] += 1
        with (state / 'client-admissions.jsonl').open('a') as out:
            out.write(json.dumps(counts)+'\n');out.flush();os.fsync(out.fileno())
        request = urllib.request.Request(GATEWAY + path, data=json.dumps(data).encode(),
            headers={'Authorization': 'Bearer '+config['master_key'], 'Content-Type': 'application/json'})
        with opener.open(request, timeout=8) as response:
            raw = response.read(32769)
            if response.status != 200 or len(raw)>32768:
                raise ValueError('bootstrap:client_response')
            return json.loads(raw)
    def issue(user, profile, purpose):
        payload = {'models': ['secure-financial-chat'], 'duration': '15m',
            'allowed_routes': ['/chat/completions'], 'max_parallel_requests': 1,
            'rpm_limit': 32, 'tpm_limit': 32768,
            'metadata': {'agent_profile': profile, 'fixture_subject': user,
                         'fixture_only': True, 'client_purpose': purpose}}
        value = call('/key/generate', payload, 'client_issuance_attempts')
        if not isinstance(value.get('key'),str) or not value['key'].startswith('sk-'):
            raise ValueError('bootstrap:client_response')
        return value['key']
    probe = issue('alpha','infrastructure','revocation-probe')
    write(state/'revocation-probe.json', {'client_key': probe, 'expires_at': config['expires_at']})
    call('/key/delete', {'keys': [probe]}, 'client_revocation_attempts')
    clients = {user: {profile: issue(user,profile,'application')
               for profile in ('infrastructure','financial')} for user in ('alpha','beta')}
    if len({key for row in clients.values() for key in row.values()} | {probe}) != 5:
        raise ValueError('bootstrap:duplicate_client')
    return clients, counts


def write(path, value):
    with path.open('x') as out:
        json.dump(value, out); out.flush(); os.fsync(out.fileno())
    path.chmod(0o600)


def run(phase):
    import psycopg
    from psycopg import sql
    config = json.loads(Path('/admission/bootstrap.json').read_text())
    required = {'owner_database_url', 'gateway_password', 'app_password', 'master_key',
                'redactor_key', 'expires_at'}
    if set(config) != required or not time.time() < config['expires_at'] <= time.time() + 900:
        raise ValueError
    fd = os.open('/state/started', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)  # Any partial provisioning prevents phase replay.
    address = '@database.google-agent-demo.svc.cluster.local:5432/'
    gateway_db = 'postgresql://portfolio_gateway:' + config['gateway_password'] + address + 'litellm'
    tenant_db = 'postgresql://portfolio_app:' + config['app_password'] + address + 'portfolio_demo'
    if phase == '--database':
        with psycopg.connect(config['owner_database_url'], connect_timeout=2, autocommit=True) as db:
            for role, password in (('portfolio_gateway', config['gateway_password']),
                                   ('portfolio_app', config['app_password'])):
                db.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}')
                           .format(sql.Identifier(role), sql.Literal(password)))
            db.execute('CREATE DATABASE litellm OWNER portfolio_gateway')
            db.execute('CREATE DATABASE portfolio_demo')
            for name, role in (('litellm', 'portfolio_gateway'), ('portfolio_demo', 'portfolio_app')):
                db.execute(sql.SQL('REVOKE CONNECT ON DATABASE {} FROM PUBLIC').format(sql.Identifier(name)))
                db.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(name), sql.Identifier(role)))
        with psycopg.connect(gateway_db, connect_timeout=2, autocommit=True) as db:
            db.execute(Path('/configuration/litellm-schema.sql').read_text())
        # The owner's URL is privately generated with the exact database suffix.
        tenant_owner = config['owner_database_url'].rsplit('/', 1)[0] + '/portfolio_demo'
        with psycopg.connect(tenant_owner, connect_timeout=2, autocommit=True) as db:
            db.execute(Path('/configuration/tenant.sql').read_text())
            fixtures = json.loads(Path('/configuration/expenses.json').read_text())
            for tenant, rows in fixtures['tenants'].items():
                for row in rows:
                    db.execute('INSERT INTO portfolio_demo.expenses(tenant_id,period,category,amount_minor_units) VALUES(%s,%s,%s,%s)',
                               (TENANTS[tenant], row['period'], row['category'], row['amount_minor_units']))
        print('{"bootstrap_phase":"database","model_requests":0,"sdk_attempts":0}')
        return
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from google.auth import crypt, jwt
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    cert = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    now = int(time.time())
    reference_key = secrets.token_hex(32)
    issued, counts = issue_clients(config, Path('/state'))
    applications = {}
    for user, tenant in (('alpha', 'fixture-a'), ('beta', 'fixture-b')):
        keys = issued[user]
        token = jwt.encode(crypt.RSASigner.from_string(pem, key_id='local-fixture'), {
            'iss': 'https://fixture-issuer.invalid', 'aud': 'portfolio-local-composition',
            'sub': 'local-fixture-' + user, 'iat': now, 'exp': int(config['expires_at']), 'tenant': tenant}).decode()
        applications['application-' + user + '.json'] = {
            'mode': 'bounded_live_synthetic', 'gateway_url': GATEWAY, 'client_keys': keys,
            'expires_at': config['expires_at'], 'certificates': {'local-fixture': cert},
            'subject': 'local-fixture-' + user, 'tenant': tenant, 'token': token,
            'tenant_reference_key': reference_key, 'tenant_directory': TENANTS,
            'tenant_database_url': tenant_db}
    applications['redactor-client.json'] = {'key': config['redactor_key']}
    # Native operator copies this exact private file into the application Secret
    # without stdout logging, then deletes this Job/Pod and bootstrap Secret.
    write(Path('/state/private-application-configurations.json'), applications)
    print(json.dumps(dict(counts, bootstrap_phase='clients', model_requests=0, sdk_attempts=0)))


if __name__ == '__main__':
    os.umask(0o077)
    if len(sys.argv) != 2 or sys.argv[1] not in {'--database', '--clients'}:
        raise SystemExit('bootstrap:phase_rejected')
    try:
        run(sys.argv[1])
    except Exception:
        print('{"status":"BLOCKED","code":"BOOTSTRAP_FAILURE","automatic_retry":false}')
        raise SystemExit(1) from None
