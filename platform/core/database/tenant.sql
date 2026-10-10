CREATE SCHEMA portfolio_demo;
CREATE TABLE portfolio_demo.expenses (
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id uuid NOT NULL,
  period text NOT NULL CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  category text NOT NULL CHECK (category IN ('office','software','transport')),
  amount_minor_units bigint NOT NULL CHECK (amount_minor_units > 0 AND amount_minor_units < 100000000)
);
ALTER TABLE portfolio_demo.expenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_demo.expenses FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_read ON portfolio_demo.expenses FOR SELECT
  USING (tenant_id = nullif(current_setting('portfolio_demo.tenant_id',true),'')::uuid);
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA portfolio_demo FROM PUBLIC;
GRANT USAGE ON SCHEMA portfolio_demo TO portfolio_app;
GRANT SELECT ON portfolio_demo.expenses TO portfolio_app;
ALTER ROLE portfolio_app SET default_transaction_read_only = on;
