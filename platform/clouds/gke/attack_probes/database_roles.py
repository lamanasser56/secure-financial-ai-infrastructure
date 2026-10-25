"""Current trusted-broker RLS/role probe. Never transfer these credentials into a worker."""
import json
from pathlib import Path

import psycopg


def probe(config, *, connect=psycopg.connect):
    out = {}
    with connect(config['read_db_url']) as db:
        out['rows_without_user'] = db.execute('SELECT count(*) FROM finance.expenses').fetchone()[0]
        db.execute("SELECT set_config('finance.user_id','00000000-0000-4000-8000-000000000000',true)")
        out['rows_unknown_user'] = db.execute('SELECT count(*) FROM finance.expenses').fetchone()[0]
    attempts = [('broker_write', 'read_db_url', 'DELETE FROM finance.expenses'),
                ('broker_users', 'read_db_url', 'SELECT password_hash FROM finance.users'),
                ('frontdoor_users', 'web_db_url', 'SELECT password_hash FROM finance.users')]
    for label, key, sql in attempts:
        db = connect(config[key])
        try:
            db.execute(sql)
            out[label] = 'ALLOWED'
        except psycopg.Error as error:
            # Permission denial and PostgreSQL's enforced read-only transaction are both explicit
            # authorization barriers; connection/SQL errors cannot masquerade as a denied write.
            out[label] = 'DENIED' if error.sqlstate in ('42501', '25006') else 'UNAVAILABLE'
        finally:
            # Even a failed security assertion must never commit a destructive statement.
            db.rollback()
            db.close()
    return out


if __name__ == '__main__':
    print(json.dumps(probe(json.loads(Path('/secrets/frontdoor/frontdoor.json').read_text()))))
