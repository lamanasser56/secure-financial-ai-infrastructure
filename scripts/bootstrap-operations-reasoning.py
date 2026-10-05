#!/usr/bin/env python3
"""Once-only DDL, one revoked probe client and one scoped catalog client."""
import json
import os
from pathlib import Path
import sys
import time
import urllib.request


def run(phase):
    config = json.loads(Path('/admission/bootstrap.json').read_text())
    if set(config) != {'owner_database_url', 'gateway_password', 'master_key', 'expires_at'} or not time.time() < config['expires_at'] <= time.time() + 900:
        raise ValueError
    with Path('/state/started').open('x') as marker:
        marker.write('once\n');marker.flush();os.fsync(marker.fileno())
    if phase == '--database':
        import psycopg
        from psycopg import sql
        with psycopg.connect(config['owner_database_url'], connect_timeout=2, autocommit=True) as db:
            db.execute(sql.SQL('CREATE ROLE portfolio_gateway LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Literal(config['gateway_password'])))
            db.execute('CREATE DATABASE litellm OWNER portfolio_gateway')
            db.execute('REVOKE CONNECT ON DATABASE litellm FROM PUBLIC')
            db.execute('GRANT CONNECT ON DATABASE litellm TO portfolio_gateway')
        url = 'postgresql://portfolio_gateway:' + config['gateway_password'] + '@database.google-agent-demo.svc.cluster.local:5432/litellm'
        with psycopg.connect(url, connect_timeout=2, autocommit=True) as db:
            db.execute(Path('/configuration/litellm-schema.sql').read_text())
        print('{"phase":"database","model_attempts":0}')
    else:
        payload = {'models': ['secure-financial-chat'], 'duration': '15m',
            'allowed_routes': ['/chat/completions'], 'max_parallel_requests': 1,
            'rpm_limit': 3, 'tpm_limit': 4096,
            'metadata': {'agent_profile': 'infrastructure', 'fixture_subject': 'operations-catalog', 'fixture_only': True}}
        counts = {'client_issuance_attempts': 0, 'client_revocation_attempts': 0, 'model_attempts': 0}
        def call(path, data, counter):
            counts[counter] += 1
            with Path('/state/client-admissions.jsonl').open('a') as out:
                out.write(json.dumps(counts) + '\n');out.flush();os.fsync(out.fileno())
            request = urllib.request.Request('http://gateway.google-agent-demo.svc.cluster.local:4000' + path,
                data=json.dumps(data).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + config['master_key']})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=8) as response:
                raw = response.read(16385)
                if response.status != 200 or len(raw) > 16384:
                    raise ValueError
                return json.loads(raw)
        def issue(name):
            data = dict(payload, metadata=dict(payload['metadata'], client_purpose=name))
            value = call('/key/generate', data, 'client_issuance_attempts')
            if type(value.get('key')) is not str or not value['key'].startswith('sk-'):
                raise ValueError
            return value['key']
        probe = issue('revocation-probe')
        with Path('/state/revocation-probe.json').open('x') as out:
            json.dump({'client_key': probe, 'expires_at': config['expires_at']},out);out.flush();os.fsync(out.fileno())
        call('/key/delete', {'keys': [probe]}, 'client_revocation_attempts')
        key = issue('catalog')
        client = {'gateway_url': 'http://gateway.google-agent-demo.svc.cluster.local:4000',
            'client_key': key, 'expires_at': config['expires_at'],
            'model_alias': 'secure-financial-chat', 'route': 'vertex_ai/gemini-2.5-flash@us-east1'}
        with Path('/state/gateway.json').open('x') as out:
            json.dump(client,out);out.flush();os.fsync(out.fileno())
        print(json.dumps(dict(counts, phase='clients')))

if __name__ == '__main__':
    os.umask(0o077)
    if len(sys.argv) != 2 or sys.argv[1] not in {'--database', '--clients'}:
        raise SystemExit('operations_bootstrap:phase_rejected')
    try:
        run(sys.argv[1])
    except Exception:
        raise SystemExit('operations_bootstrap:blocked; no automatic replay') from None
