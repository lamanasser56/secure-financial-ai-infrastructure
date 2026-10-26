"""Current frontdoor/finance boundary probes for D05, D06, and D07.

Each remote script reads its own in-Pod credentials, emits booleans only, and
does not make an external LLM or Google SDP call.
"""
from live_probe_kube import one_pod, python_probe


D05 = r'''
import json
from pathlib import Path
import psycopg
c = json.loads(Path('/secrets/frontdoor/frontdoor.json').read_text())
with psycopg.connect(c['web_db_url'], connect_timeout=5) as db:
    role = db.execute('select current_user').fetchone()[0]
    known = db.execute('select count(*) from finance.login_lookup(%s)', ('lama',)).fetchone()[0]
    unknown = db.execute('select count(*) from finance.login_lookup(%s)', ('assessment_unknown',)).fetchone()[0]
    legacy = dict(db.execute("select rolname, rolcanlogin from pg_roles where rolname in ('finance_web','finance_agent')").fetchall())
    connect = [db.execute('select has_database_privilege(%s, current_database(), %s)',
                          (name, 'CONNECT')).fetchone()[0] for name in ('finance_web', 'finance_agent')]
    users_read = db.execute("select has_table_privilege(current_user, 'finance.users', 'SELECT')").fetchone()[0]
print(json.dumps({'frontdoor_role': role == 'finance_frontdoor', 'known_lookup_one': known == 1,
                  'unknown_lookup_none': unknown == 0,
                  'legacy_login_disabled': set(legacy) == {'finance_web','finance_agent'} and not any(legacy.values()),
                  'legacy_connect_disabled': not any(connect), 'users_table_read_denied': not users_read}))
'''

D06 = r'''
import json
from pathlib import Path
import psycopg
c = json.loads(Path('/secrets/frontdoor/frontdoor.json').read_text())
with psycopg.connect(c['web_db_url'], connect_timeout=5) as web:
    ids = {name: web.execute('select id::text from finance.login_lookup(%s)', (name,)).fetchone()[0]
           for name in ('lama', 'sara')}
with psycopg.connect(c['read_db_url'], connect_timeout=5) as db:
    result = {'broker_role': db.execute('select current_user').fetchone()[0] == 'finance_data_broker',
              'initial_no_context': db.execute('select count(*) from finance.expenses').fetchone()[0] == 0}
    db.commit()
    for name in ('lama', 'sara'):
        other = 'sara' if name == 'lama' else 'lama'
        with db.transaction():
            db.execute("select set_config('finance.user_id', %s, true)", (ids[name],))
            own = db.execute('select count(*) from finance.expenses').fetchone()[0]
            cross = db.execute('select count(*) from finance.expenses where user_id=%s', (ids[other],)).fetchone()[0]
        cleared = db.execute('select count(*) from finance.expenses').fetchone()[0]
        setting = db.execute("select current_setting('finance.user_id', true)").fetchone()[0]
        db.commit()
        result[name + '_own_only'] = own >= 1 and cross == 0
        result[name + '_context_cleared'] = cleared == 0 and setting in (None, '')
print(json.dumps(result))
'''

D07 = r'''
import json
from pathlib import Path
import psycopg
c = json.loads(Path('/secrets/frontdoor/frontdoor.json').read_text())
dsn = c['read_db_url']
with psycopg.connect(dsn, connect_timeout=5) as db:
    settings = {name: db.execute('show ' + name).fetchone()[0] for name in
                ('default_transaction_read_only','statement_timeout','idle_in_transaction_session_timeout','lock_timeout')}
    role = db.execute('select current_user').fetchone()[0]
def refused(statement):
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as db:
        db.execute('begin')
        try:
            db.execute(statement)
            denied = False
        except psycopg.Error:
            denied = True
        finally:
            db.execute('rollback')
    return denied
result = {'broker_role': role == 'finance_data_broker',
          'read_only': settings['default_transaction_read_only'] == 'on',
          'statement_timeout': settings['statement_timeout'] == '2s',
          'idle_timeout': settings['idle_in_transaction_session_timeout'] == '5s',
          'lock_timeout': settings['lock_timeout'] == '1s',
          'temp_denied': refused('create temp table assessment_probe (x int)'),
          'schema_denied': refused('create schema assessment_probe'),
          'users_read_denied': refused('select * from finance.users limit 1'),
          'set_role_denied': refused('set role finance_frontdoor'),
          'session_auth_denied': refused('set session authorization finance_frontdoor'),
          'auth_catalog_denied': refused('select * from pg_authid limit 1')}
print(json.dumps(result))
'''

SCRIPTS = {'D05': D05, 'D06': D06, 'D07': D07}


def probe(case, kubeconfig, *, executable='kubectl', pod=one_pod, execute=python_probe):
    if case not in SCRIPTS:
        raise ValueError('assessment:unknown_finance_probe')
    name = pod(kubeconfig, 'apps', 'app.kubernetes.io/name=financial-frontdoor',
               executable=executable)
    return execute(kubeconfig, 'apps', name, SCRIPTS[case], executable=executable)
