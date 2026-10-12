"""Financial Agent database against a real Postgres: row-level security per user, read-only agent role.

Needs a Postgres superuser DSN in FINANCE_TEST_DSN (CI: a digest-pinned postgres service) or the `pgserver`
package (local); skipped otherwise. Runs the real bootstrap code (bootstrap.finance) and finance.sql.
"""
import os
from pathlib import Path
import tempfile
import unittest
import uuid

REPO = Path(__file__).resolve().parents[3]
try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


def server_dsn():
    if os.environ.get('FINANCE_TEST_DSN'):
        return os.environ['FINANCE_TEST_DSN'], None
    try:
        import pgserver
    except ImportError:
        return None, None
    server = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode='stop')
    return server.get_uri(), server


HASH = '$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHRzYWx0$aGFzaGhhc2hoYXNoaGFzaGhhc2hoYXNoaGFzaGhhc2g'
USERS = [{'id': str(uuid.uuid4()), 'username': u, 'display_name': u.title(), 'password_hash': HASH} for u in ('lama', 'sara')]


@unittest.skipUnless(psycopg is not None, 'psycopg needed')
class FinanceDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn, cls.server = server_dsn()
        if cls.dsn is None:
            raise unittest.SkipTest('set FINANCE_TEST_DSN or install pgserver')
        from agent_platform.programs import bootstrap
        bootstrap.SQL = REPO / 'platform/core/database'
        cls.config = {'finance': {'web_password': 'web-' + uuid.uuid4().hex, 'agent_password': 'agent-' + uuid.uuid4().hex, 'users': USERS}}
        info = psycopg.conninfo.conninfo_to_dict(cls.dsn)

        def connect(database):
            return psycopg.connect(**dict(info, dbname=database), autocommit=True)
        bootstrap.finance(cls.config, connect=connect)
        bootstrap.finance(cls.config, connect=connect)  # idempotent
        cls.as_role = lambda cls_, role: psycopg.connect(**dict(info, dbname='finance', user=role,
                                                               password=cls.config['finance'][role.split('_')[1] + '_password']))

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, 'server', None) is not None:
            cls.server.cleanup()

    def add(self, user, merchant, amount):
        with self.as_role('finance_web') as db:
            db.execute("SELECT set_config('finance.user_id', %s, true)", (user['id'],))
            db.execute("INSERT INTO finance.expenses(spent_on, merchant, category, amount_minor) VALUES ('2026-10-01', %s, 'food', %s)",
                       (merchant, amount))

    def rows(self, role, user):
        with self.as_role(role) as db:
            if user is not None:
                db.execute("SELECT set_config('finance.user_id', %s, true)", (user['id'],))
            return [r[0] for r in db.execute('SELECT merchant FROM finance.expenses ORDER BY id').fetchall()]

    def test_each_user_sees_only_their_own_rows(self):
        lama, sara = USERS
        self.add(lama, 'Lama cafe', 2400)
        self.add(sara, 'Sara market', 9900)
        for role in ('finance_web', 'finance_agent'):
            with self.subTest(role):
                self.assertIn('Lama cafe', self.rows(role, lama))
                self.assertNotIn('Sara market', self.rows(role, lama))
                self.assertEqual(self.rows(role, None), [])  # no user set: nothing visible

    def test_web_cannot_insert_for_another_user(self):
        lama, sara = USERS
        with self.as_role('finance_web') as db, self.assertRaises(psycopg.Error):
            db.execute("SELECT set_config('finance.user_id', %s, true)", (lama['id'],))
            db.execute("INSERT INTO finance.expenses(user_id, spent_on, merchant, category, amount_minor) VALUES (%s, '2026-10-01', 'x', 'food', 100)",
                       (sara['id'],))

    def test_agent_is_read_only_and_cannot_see_users(self):
        lama, _ = USERS
        for statement in ("INSERT INTO finance.expenses(spent_on, merchant, category, amount_minor) VALUES ('2026-10-01', 'x', 'food', 100)",
                          'DELETE FROM finance.expenses', "UPDATE finance.expenses SET amount_minor = 1",
                          'SELECT password_hash FROM finance.users'):
            with self.subTest(statement), self.as_role('finance_agent') as db, self.assertRaises(psycopg.Error):
                db.execute("SELECT set_config('finance.user_id', %s, true)", (lama['id'],))
                db.execute(statement)

    def test_web_reads_one_users_hash_only_through_the_lookup_function(self):
        lama, sara = USERS
        with self.as_role('finance_web') as db, self.assertRaises(psycopg.Error):
            db.execute('SELECT password_hash FROM finance.users')  # no table access
        with self.as_role('finance_web') as db:
            rows = db.execute('SELECT id::text, password_hash FROM finance.login_lookup(%s)', ('lama',)).fetchall()
            self.assertEqual(rows, [(lama['id'], HASH)])
            self.assertEqual(db.execute('SELECT count(*) FROM finance.login_lookup(%s)', ("' OR '1'='1",)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM finance.login_lookup('%')").fetchone()[0], 0)  # exact match only
        with self.as_role('finance_agent') as db, self.assertRaises(psycopg.Error):
            db.execute('SELECT * FROM finance.login_lookup(%s)', ('lama',))  # the agent role cannot call it

    def test_lookup_function_contract(self):
        """Owner is a NOLOGIN, non-superuser role; SECURITY DEFINER; pinned search_path; EXECUTE only for finance_web."""
        info = psycopg.conninfo.conninfo_to_dict(self.dsn)
        with psycopg.connect(**dict(info, dbname='finance')) as db:
            row = db.execute(
                "SELECT r.rolname, r.rolcanlogin, r.rolsuper, r.rolbypassrls, p.prosecdef, p.proconfig, "
                "has_function_privilege('finance_web', p.oid, 'EXECUTE'), has_function_privilege('finance_agent', p.oid, 'EXECUTE'), "
                "(SELECT count(*) FROM aclexplode(p.proacl) a WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'), "
                "has_table_privilege('finance_owner', 'finance.expenses', 'SELECT') "
                "FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner WHERE p.oid = 'finance.login_lookup(text)'::regprocedure").fetchone()
        self.assertEqual(row, ('finance_owner', False, False, False, True, ['search_path=pg_catalog, finance'], True, False, 0, False))

    def test_web_cannot_change_or_delete(self):
        lama, _ = USERS
        for statement in ('DELETE FROM finance.expenses', 'UPDATE finance.expenses SET amount_minor = 1'):
            with self.subTest(statement), self.as_role('finance_web') as db, self.assertRaises(psycopg.Error):
                db.execute("SELECT set_config('finance.user_id', %s, true)", (lama['id'],))
                db.execute(statement)


if __name__ == '__main__':
    unittest.main()
