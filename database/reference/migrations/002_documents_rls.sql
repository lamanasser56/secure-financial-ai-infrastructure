BEGIN;

ALTER TABLE portfolio_ref.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_ref.documents FORCE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_select
  ON portfolio_ref.documents
  AS PERMISSIVE
  FOR SELECT
  TO PUBLIC
  USING (
    tenant_id = NULLIF(
      pg_catalog.btrim(pg_catalog.current_setting('portfolio_ref.tenant_id', true)),
      ''
    )::uuid
  );

CREATE POLICY documents_tenant_insert
  ON portfolio_ref.documents
  AS PERMISSIVE
  FOR INSERT
  TO PUBLIC
  WITH CHECK (
    tenant_id = NULLIF(
      pg_catalog.btrim(pg_catalog.current_setting('portfolio_ref.tenant_id', true)),
      ''
    )::uuid
  );

CREATE POLICY documents_tenant_update
  ON portfolio_ref.documents
  AS PERMISSIVE
  FOR UPDATE
  TO PUBLIC
  USING (
    tenant_id = NULLIF(
      pg_catalog.btrim(pg_catalog.current_setting('portfolio_ref.tenant_id', true)),
      ''
    )::uuid
  )
  WITH CHECK (
    tenant_id = NULLIF(
      pg_catalog.btrim(pg_catalog.current_setting('portfolio_ref.tenant_id', true)),
      ''
    )::uuid
  );

CREATE POLICY documents_tenant_delete
  ON portfolio_ref.documents
  AS PERMISSIVE
  FOR DELETE
  TO PUBLIC
  USING (
    tenant_id = NULLIF(
      pg_catalog.btrim(pg_catalog.current_setting('portfolio_ref.tenant_id', true)),
      ''
    )::uuid
  );

COMMIT;
