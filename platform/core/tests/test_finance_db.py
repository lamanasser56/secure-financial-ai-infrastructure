"""Financial Agent database against a real Postgres: row-level security per user, trusted broker roles; untrusted workers hold no database identity.

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
        cls.config = {'finance': {'broker_web_password': 'web-' + uuid.uuid4().hex, 'broker_read_password': 'agent-' + uuid.uuid4().hex, 'users': USERS}}
        info = psycopg.conninfo.conninfo_to_dict(cls.dsn)

        def connect(database):
            return psycopg.connect(**dict(info, dbname=database), autocommit=True)
        bootstrap.finance(cls.config, connect=connect)
        bootstrap.finance(cls.config, connect=connect)  # idempotent
        cls.as_role = lambda cls_, role: psycopg.connect(**dict(info, dbname='finance', user=role,
                                                               password=cls.config['finance']['broker_web_password' if role == 'finance_frontdoor' else 'broker_read_password']))

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, 'server', None) is not None:
            cls.server.cleanup()

    def test_current_live_attack_role_probe_uses_the_real_broker_roles(self):
        import sys
        sys.path.insert(0, str(REPO / 'platform/clouds/gke'))
        from attack_probes.database_roles import probe
        result = probe({'read_db_url': 'read', 'web_db_url': 'web'},
            connect=lambda role: self.as_role('finance_data_broker' if role == 'read' else 'finance_frontdoor'))
        self.assertEqual(result, {'rows_without_user': 0, 'rows_unknown_user': 0, 'broker_write': 'DENIED',
                                 'broker_users': 'DENIED', 'frontdoor_users': 'DENIED'})

    def test_attack_fixture_cleanup_is_exact_idempotent_and_preserves_unowned_rows(self):
        import sys
        sys.path.insert(0,str(REPO/'platform/clouds/gke'))
        from attack_fixtures import FixtureRows
        fixture=FixtureRows(None,None)
        info=psycopg.conninfo.conninfo_to_dict(self.dsn)
        ids=[]
        with psycopg.connect(**dict(info,dbname='finance'),autocommit=True) as owner:
            try:
                for tag in (fixture.tag,'not-owned-by-this-run'):
                    ids.append(owner.execute("INSERT INTO finance.expenses(user_id,spent_on,merchant,category,amount_minor,note) VALUES (%s,'2035-11-02',%s,'food',2450,%s) RETURNING id",
                        (USERS[0]['id'],"Owner's Cafe",tag)).fetchone()[0])
                fixture.rows=[{'user':USERS[0]['id'],'id':ids[0],'entry':{'spent_on':'2035-11-02','merchant':"Owner's Cafe",'category':'food','amount':'24.50'}}]
                sql='\n'.join(line for line in fixture.cleanup_sql().splitlines() if not line.startswith('\\'))
                owner.execute(sql)
                owner.execute(sql)  # A lost response or a repeated cleanup cannot turn success into an orphan.
                self.assertEqual(owner.execute('SELECT id FROM finance.expenses WHERE id=ANY(%s)',(ids,)).fetchall(),[(ids[1],)])
            finally:
                owner.rollback()
                owner.execute('DELETE FROM finance.expenses WHERE id=ANY(%s)',(ids,))

    def test_attack_fixture_cleanup_owns_unknown_insert_id_after_a_lost_response(self):
        import sys
        sys.path.insert(0,str(REPO/'platform/clouds/gke'))
        from attack_fixtures import FixtureRows
        fixture=FixtureRows(None,None)
        info=psycopg.conninfo.conninfo_to_dict(self.dsn)
        entry={'spent_on':'2035-11-04','merchant':'Owner scope probe','category':'food','amount':'1.00'}
        # A broken handler could use either identity. Both are explicitly tracked before
        # the adversarial request, with no assumption that an HTTP response delivered its ID.
        fixture.rows=[{'user':u['id'],'id':None,'entry':entry} for u in USERS]
        with psycopg.connect(**dict(info,dbname='finance'),autocommit=True) as owner:
            try:
                owner.execute("INSERT INTO finance.expenses(user_id,spent_on,merchant,category,amount_minor,note) VALUES (%s,'2035-11-04','Owner scope probe','food',100,%s)",(USERS[1]['id'],fixture.tag))
                sql='\n'.join(line for line in fixture.cleanup_sql().splitlines() if not line.startswith('\\'))
                owner.execute(sql)
                self.assertEqual(owner.execute('SELECT count(*) FROM finance.expenses WHERE note=%s',(fixture.tag,)).fetchone()[0],0)
            finally:
                owner.rollback()
                owner.execute('DELETE FROM finance.expenses WHERE note=%s',(fixture.tag,))

    def test_attack_fixture_cleanup_refuses_changed_ownership_and_rolls_back(self):
        import sys
        sys.path.insert(0,str(REPO/'platform/clouds/gke'))
        from attack_fixtures import FixtureRows
        fixture=FixtureRows(None,None)
        info=psycopg.conninfo.conninfo_to_dict(self.dsn)
        with psycopg.connect(**dict(info,dbname='finance'),autocommit=True) as owner:
            expense=owner.execute("INSERT INTO finance.expenses(user_id,spent_on,merchant,category,amount_minor,note) VALUES (%s,'2035-11-02','Cafe Nadia','food',2450,'operator-edited') RETURNING id",(USERS[0]['id'],)).fetchone()[0]
            try:
                fixture.rows=[{'user':USERS[0]['id'],'id':expense,'entry':{'spent_on':'2035-11-02','merchant':'Cafe Nadia','category':'food','amount':'24.50'}}]
                sql='\n'.join(line for line in fixture.cleanup_sql().splitlines() if not line.startswith('\\'))
                with self.assertRaises(psycopg.Error): owner.execute(sql)
                owner.rollback()
                self.assertEqual(owner.execute('SELECT note FROM finance.expenses WHERE id=%s',(expense,)).fetchone()[0],'operator-edited')
            finally:
                owner.rollback()
                owner.execute('DELETE FROM finance.expenses WHERE id=%s',(expense,))

    def add(self, user, merchant, amount):
        with self.as_role('finance_frontdoor') as db:
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
        for role in ('finance_frontdoor', 'finance_data_broker'):
            with self.subTest(role):
                self.assertIn('Lama cafe', self.rows(role, lama))
                self.assertNotIn('Sara market', self.rows(role, lama))
                self.assertEqual(self.rows(role, None), [])  # no user set: nothing visible

    def test_reused_broker_connection_clears_scoped_identity(self):
        """D06: query the same connection after SET LOCAL's transaction ends."""
        lama, _ = USERS
        self.add(lama, 'D06 synthetic expense', 100)
        info = psycopg.conninfo.conninfo_to_dict(self.dsn)
        with psycopg.connect(**dict(info, dbname='finance', user='finance_data_broker',
                                   password=self.config['finance']['broker_read_password']),
                             autocommit=True) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM finance.expenses').fetchone()[0], 0)
            with db.transaction():
                db.execute("SELECT set_config('finance.user_id', %s, true)", (lama['id'],))
                self.assertGreaterEqual(db.execute('SELECT count(*) FROM finance.expenses').fetchone()[0], 1)
                db.execute("SELECT set_config('finance.user_id', '', true)")
                self.assertEqual(db.execute('SELECT count(*) FROM finance.expenses').fetchone()[0], 0)
            # This is the step omitted from the earlier live D06 probe.
            self.assertEqual(db.execute('SELECT count(*) FROM finance.expenses').fetchone()[0], 0)

    def test_web_cannot_insert_for_another_user(self):
        lama, sara = USERS
        with self.as_role('finance_frontdoor') as db, self.assertRaises(psycopg.Error):
            db.execute("SELECT set_config('finance.user_id', %s, true)", (lama['id'],))
            db.execute("INSERT INTO finance.expenses(user_id, spent_on, merchant, category, amount_minor) VALUES (%s, '2026-10-01', 'x', 'food', 100)",
                       (sara['id'],))

    def test_agent_is_read_only_and_cannot_see_users(self):
        lama, _ = USERS
        for statement in ("INSERT INTO finance.expenses(spent_on, merchant, category, amount_minor) VALUES ('2026-10-01', 'x', 'food', 100)",
                          'DELETE FROM finance.expenses', "UPDATE finance.expenses SET amount_minor = 1",
                          'SELECT password_hash FROM finance.users'):
            with self.subTest(statement), self.as_role('finance_data_broker') as db, self.assertRaises(psycopg.Error):
                db.execute("SELECT set_config('finance.user_id', %s, true)", (lama['id'],))
                db.execute(statement)

    def test_web_reads_one_users_hash_only_through_the_lookup_function(self):
        lama, sara = USERS
        with self.as_role('finance_frontdoor') as db, self.assertRaises(psycopg.Error):
            db.execute('SELECT password_hash FROM finance.users')  # no table access
        with self.as_role('finance_frontdoor') as db:
            rows = db.execute('SELECT id::text, password_hash FROM finance.login_lookup(%s)', ('lama',)).fetchall()
            self.assertEqual(rows, [(lama['id'], HASH)])
            self.assertEqual(db.execute('SELECT count(*) FROM finance.login_lookup(%s)', ("' OR '1'='1",)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM finance.login_lookup('%')").fetchone()[0], 0)  # exact match only
        with self.as_role('finance_data_broker') as db, self.assertRaises(psycopg.Error):
            db.execute('SELECT * FROM finance.login_lookup(%s)', ('lama',))  # the agent role cannot call it

    def test_lookup_function_contract(self):
        """Owner is a NOLOGIN, non-superuser role; SECURITY DEFINER; pinned search_path; EXECUTE only for trusted finance_frontdoor."""
        info = psycopg.conninfo.conninfo_to_dict(self.dsn)
        with psycopg.connect(**dict(info, dbname='finance')) as db:
            row = db.execute(
                "SELECT r.rolname, r.rolcanlogin, r.rolsuper, r.rolbypassrls, p.prosecdef, p.proconfig, "
                "has_function_privilege('finance_frontdoor', p.oid, 'EXECUTE'), has_function_privilege('finance_data_broker', p.oid, 'EXECUTE'), "
                "(SELECT count(*) FROM aclexplode(p.proacl) a WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'), "
                "has_table_privilege('finance_owner', 'finance.expenses', 'SELECT') "
                "FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner WHERE p.oid = 'finance.login_lookup(text)'::regprocedure").fetchone()
        self.assertEqual(row, ('finance_owner', False, False, False, True, ['search_path=pg_catalog, finance'], True, False, 0, False))

    def test_web_cannot_change_or_delete(self):
        lama, _ = USERS
        for statement in ('DELETE FROM finance.expenses', 'UPDATE finance.expenses SET amount_minor = 1'):
            with self.subTest(statement), self.as_role('finance_frontdoor') as db, self.assertRaises(psycopg.Error):
                db.execute("SELECT set_config('finance.user_id', %s, true)", (lama['id'],))
                db.execute(statement)


if __name__ == '__main__':
    unittest.main()
