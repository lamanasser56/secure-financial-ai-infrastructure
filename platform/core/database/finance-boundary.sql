-- Reviewed v2 cutover only: run by the schema owner after agent DB paths are quarantined.
-- No user data is copied/deleted. Old agents keep neither grants nor usable login credentials.
ALTER ROLE finance_web NOLOGIN PASSWORD NULL;
ALTER ROLE finance_agent NOLOGIN PASSWORD NULL;
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
  WHERE usename IN ('finance_web', 'finance_agent') AND pid <> pg_backend_pid();
REVOKE ALL ON DATABASE finance FROM finance_web, finance_agent;
REVOKE ALL ON SCHEMA finance FROM finance_web, finance_agent;
REVOKE ALL ON ALL TABLES IN SCHEMA finance FROM finance_web, finance_agent;
REVOKE INSERT (spent_on, merchant, category, amount_minor, note) ON finance.expenses FROM finance_web;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA finance FROM finance_web, finance_agent;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA finance FROM finance_web, finance_agent;
REVOKE CREATE, TEMPORARY ON DATABASE finance FROM PUBLIC;
GRANT CONNECT ON DATABASE finance TO finance_frontdoor, finance_data_broker;
GRANT USAGE ON SCHEMA finance TO finance_frontdoor, finance_data_broker;
GRANT SELECT ON finance.expenses TO finance_frontdoor, finance_data_broker;
GRANT INSERT (spent_on, merchant, category, amount_minor, note) ON finance.expenses TO finance_frontdoor;
GRANT EXECUTE ON FUNCTION finance.login_lookup(text) TO finance_frontdoor;
DROP POLICY IF EXISTS own_rows_read ON finance.expenses;
CREATE POLICY own_rows_read ON finance.expenses FOR SELECT TO finance_frontdoor, finance_data_broker
  USING (user_id = nullif(current_setting('finance.user_id', true), '')::uuid);
DROP POLICY IF EXISTS own_rows_insert ON finance.expenses;
CREATE POLICY own_rows_insert ON finance.expenses FOR INSERT TO finance_frontdoor
  WITH CHECK (user_id = nullif(current_setting('finance.user_id', true), '')::uuid);
ALTER ROLE finance_data_broker SET default_transaction_read_only = on;
ALTER ROLE finance_data_broker SET statement_timeout = '2s';
ALTER ROLE finance_frontdoor SET statement_timeout = '2s';
ALTER ROLE finance_data_broker SET idle_in_transaction_session_timeout = '5s';
ALTER ROLE finance_frontdoor SET idle_in_transaction_session_timeout = '5s';
ALTER ROLE finance_data_broker SET lock_timeout = '1s';
ALTER ROLE finance_frontdoor SET lock_timeout = '1s';
