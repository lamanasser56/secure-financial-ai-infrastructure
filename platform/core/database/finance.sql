-- Financial Agent data (platform/agents/financial/agent.yaml). Run once by the bootstrap job as the database owner.
-- Users enter their own expenses through the agent's web API (role finance_web); the agent's tools read them through a
-- read-only role (finance_agent). Both roles are non-owner and NOBYPASSRLS, and every row is visible only to the user
-- whose id the server sets per transaction (SET LOCAL finance.user_id), never to the model or the browser.
CREATE SCHEMA finance;

CREATE TABLE finance.users (
  id uuid PRIMARY KEY,
  username text NOT NULL UNIQUE CHECK (username ~ '^[a-z][a-z0-9_]{2,19}$'),
  display_name text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 40),
  password_hash text NOT NULL CHECK (password_hash LIKE '$argon2id$%')
);

CREATE TABLE finance.expenses (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id uuid NOT NULL DEFAULT nullif(current_setting('finance.user_id', true), '')::uuid REFERENCES finance.users(id),
  spent_on date NOT NULL CHECK (spent_on BETWEEN DATE '2020-01-01' AND DATE '2035-12-31'),
  merchant text NOT NULL CHECK (length(merchant) BETWEEN 1 AND 60),
  category text NOT NULL CHECK (category IN ('food', 'transport', 'shopping', 'bills', 'health', 'travel', 'other')),
  amount_minor bigint NOT NULL CHECK (amount_minor > 0 AND amount_minor <= 10000000),
  note text NOT NULL DEFAULT '' CHECK (length(note) <= 200),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX expenses_user_date ON finance.expenses (user_id, spent_on);

ALTER TABLE finance.expenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.expenses FORCE ROW LEVEL SECURITY;
CREATE POLICY own_rows_read ON finance.expenses FOR SELECT
  USING (user_id = nullif(current_setting('finance.user_id', true), '')::uuid);
CREATE POLICY own_rows_insert ON finance.expenses FOR INSERT
  WITH CHECK (user_id = nullif(current_setting('finance.user_id', true), '')::uuid);

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA finance FROM PUBLIC;
GRANT USAGE ON SCHEMA finance TO finance_web, finance_agent;
-- Web API: sign-in lookup, then the signed-in user's own rows (insert without choosing user_id: it comes from the setting).
GRANT SELECT ON finance.users TO finance_web;
GRANT SELECT ON finance.expenses TO finance_web;
GRANT INSERT (spent_on, merchant, category, amount_minor, note) ON finance.expenses TO finance_web;
-- Agent tools: read the signed-in user's own expenses only; no access to users or password hashes; no writes.
GRANT SELECT ON finance.expenses TO finance_agent;
ALTER ROLE finance_agent SET default_transaction_read_only = on;
ALTER ROLE finance_agent SET statement_timeout = '2s';
ALTER ROLE finance_web SET statement_timeout = '2s';
