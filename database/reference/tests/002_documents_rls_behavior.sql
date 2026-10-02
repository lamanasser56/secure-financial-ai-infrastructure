-- DISPOSABLE VALIDATION ONLY. This script creates synthetic rows, NOLOGIN
-- validation roles, temporary ownership, and minimum test grants inside a
-- transaction that is rolled back. It is not production role provisioning.

CREATE TEMPORARY TABLE portfolio_ref_rls_validation_baseline
ON COMMIT PRESERVE ROWS
AS
SELECT documents.relowner, documents.relacl, namespace.nspacl
FROM pg_class AS documents
JOIN pg_namespace AS namespace
  ON namespace.oid = documents.relnamespace
WHERE documents.oid = to_regclass('portfolio_ref.documents');

BEGIN;
SET LOCAL portfolio_ref.tenant_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
DO $validation$
BEGIN
  IF pg_catalog.current_setting('portfolio_ref.tenant_id', true)
       <> 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' THEN
    RAISE EXCEPTION 'transaction-local tenant context was not set';
  END IF;
END
$validation$;
COMMIT;

DO $validation$
BEGIN
  IF NULLIF(
       pg_catalog.btrim(pg_catalog.current_setting('portfolio_ref.tenant_id', true)),
       ''
     ) IS NOT NULL THEN
    RAISE EXCEPTION 'transaction-local tenant context survived commit';
  END IF;
END
$validation$;

BEGIN;
SET LOCAL portfolio_ref.tenant_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
ROLLBACK;

DO $validation$
BEGIN
  IF NULLIF(
       pg_catalog.btrim(pg_catalog.current_setting('portfolio_ref.tenant_id', true)),
       ''
     ) IS NOT NULL THEN
    RAISE EXCEPTION 'transaction-local tenant context survived rollback';
  END IF;
END
$validation$;

BEGIN;

CREATE ROLE portfolio_ref_rls_validation_owner
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE portfolio_ref_rls_validation_runtime
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;

INSERT INTO portfolio_ref.tenants (id)
VALUES
  ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
  ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');

SET LOCAL portfolio_ref.tenant_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
INSERT INTO portfolio_ref.documents (tenant_id, id, object_key, sha256_digest)
VALUES (
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  '11111111-1111-4111-8111-111111111111',
  'validation/tenant-a/original',
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
);

SET LOCAL portfolio_ref.tenant_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
INSERT INTO portfolio_ref.documents (tenant_id, id, object_key, sha256_digest)
VALUES (
  'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  '22222222-2222-4222-8222-222222222222',
  'validation/tenant-b/original',
  'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
);

ALTER TABLE portfolio_ref.documents OWNER TO portfolio_ref_rls_validation_owner;
GRANT USAGE ON SCHEMA portfolio_ref
  TO portfolio_ref_rls_validation_owner, portfolio_ref_rls_validation_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON portfolio_ref.documents
  TO portfolio_ref_rls_validation_runtime;

DO $validation$
DECLARE
  runtime_oid oid;
  owner_oid oid;
  runtime_record record;
BEGIN
  SELECT oid, rolsuper, rolinherit, rolbypassrls
  INTO runtime_record
  FROM pg_roles
  WHERE rolname = 'portfolio_ref_rls_validation_runtime';

  runtime_oid := runtime_record.oid;

  SELECT relowner INTO owner_oid
  FROM pg_class
  WHERE oid = to_regclass('portfolio_ref.documents');

  IF runtime_oid = owner_oid THEN
    RAISE EXCEPTION 'validation runtime role owns the documents table';
  END IF;
  IF runtime_record.rolsuper THEN
    RAISE EXCEPTION 'validation runtime role is a superuser';
  END IF;
  IF runtime_record.rolbypassrls THEN
    RAISE EXCEPTION 'validation runtime role has BYPASSRLS';
  END IF;
  IF runtime_record.rolinherit THEN
    RAISE EXCEPTION 'validation runtime role has INHERIT';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_roles AS privileged_role
    WHERE privileged_role.oid <> runtime_oid
      AND (
        privileged_role.rolsuper
        OR privileged_role.rolbypassrls
        OR privileged_role.rolcreaterole
        OR privileged_role.rolcreatedb
        OR privileged_role.oid = owner_oid
      )
      AND pg_catalog.pg_has_role(
        runtime_oid,
        privileged_role.oid,
        'MEMBER'
      )
  ) THEN
    RAISE EXCEPTION 'validation runtime role is a member of a privileged role';
  END IF;
END
$validation$;

SET ROLE portfolio_ref_rls_validation_owner;
SET LOCAL portfolio_ref.tenant_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
DO $validation$
DECLARE
  visible_count integer;
BEGIN
  SELECT count(*) INTO visible_count FROM portfolio_ref.documents;
  IF visible_count <> 1 THEN
    RAISE EXCEPTION 'FORCE RLS did not constrain the table owner';
  END IF;
END
$validation$;
RESET ROLE;

SET ROLE portfolio_ref_rls_validation_runtime;
RESET portfolio_ref.tenant_id;

DO $validation$
DECLARE
  visible_count integer;
  affected_count integer;
BEGIN
  SELECT count(*) INTO visible_count FROM portfolio_ref.documents;
  IF visible_count <> 0 THEN
    RAISE EXCEPTION 'missing tenant context exposed rows';
  END IF;

  UPDATE portfolio_ref.documents
  SET object_key = object_key
  WHERE tenant_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  GET DIAGNOSTICS affected_count = ROW_COUNT;
  IF affected_count <> 0 THEN
    RAISE EXCEPTION 'missing tenant context updated rows';
  END IF;

  DELETE FROM portfolio_ref.documents
  WHERE tenant_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  GET DIAGNOSTICS affected_count = ROW_COUNT;
  IF affected_count <> 0 THEN
    RAISE EXCEPTION 'missing tenant context deleted rows';
  END IF;

  BEGIN
    INSERT INTO portfolio_ref.documents (tenant_id, id, object_key, sha256_digest)
    VALUES (
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      '66666666-6666-4666-8666-666666666666',
      'validation/missing-context/original',
      'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'
    );
    RAISE EXCEPTION 'missing tenant context inserted a row';
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;
END
$validation$;

SET LOCAL portfolio_ref.tenant_id = '';
DO $validation$
DECLARE
  visible_count integer;
BEGIN
  SELECT count(*) INTO visible_count FROM portfolio_ref.documents;
  IF visible_count <> 0 THEN
    RAISE EXCEPTION 'empty tenant context exposed rows';
  END IF;

  BEGIN
    INSERT INTO portfolio_ref.documents (tenant_id, id, object_key, sha256_digest)
    VALUES (
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      '77777777-7777-4777-8777-777777777777',
      'validation/empty-context/original',
      '1111111111111111111111111111111111111111111111111111111111111111'
    );
    RAISE EXCEPTION 'empty tenant context inserted a row';
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;
END
$validation$;

SET LOCAL portfolio_ref.tenant_id = '   ';
DO $validation$
DECLARE
  visible_count integer;
BEGIN
  SELECT count(*) INTO visible_count FROM portfolio_ref.documents;
  IF visible_count <> 0 THEN
    RAISE EXCEPTION 'whitespace tenant context exposed rows';
  END IF;

  BEGIN
    INSERT INTO portfolio_ref.documents (tenant_id, id, object_key, sha256_digest)
    VALUES (
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      '88888888-8888-4888-8888-888888888888',
      'validation/whitespace-context/original',
      '2222222222222222222222222222222222222222222222222222222222222222'
    );
    RAISE EXCEPTION 'whitespace tenant context inserted a row';
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;
END
$validation$;

SET LOCAL portfolio_ref.tenant_id = 'not-a-uuid';
DO $validation$
BEGIN
  BEGIN
    PERFORM count(*) FROM portfolio_ref.documents;
    RAISE EXCEPTION 'malformed tenant context did not fail';
  EXCEPTION
    WHEN invalid_text_representation THEN NULL;
  END;
END
$validation$;

SET LOCAL portfolio_ref.tenant_id = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
DO $validation$
DECLARE
  visible_count integer;
BEGIN
  SELECT count(*) INTO visible_count FROM portfolio_ref.documents;
  IF visible_count <> 0 THEN
    RAISE EXCEPTION 'unknown tenant context exposed rows';
  END IF;

  BEGIN
    INSERT INTO portfolio_ref.documents (tenant_id, id, object_key, sha256_digest)
    VALUES (
      'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
      '33333333-3333-4333-8333-333333333333',
      'validation/unknown/original',
      'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'
    );
    RAISE EXCEPTION 'unknown tenant insert did not fail';
  EXCEPTION
    WHEN foreign_key_violation THEN NULL;
  END;
END
$validation$;

SAVEPOINT tenant_a_transaction_scope;
SET LOCAL portfolio_ref.tenant_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
DO $validation$
DECLARE
  visible_count integer;
  affected_count integer;
BEGIN
  SELECT count(*) INTO visible_count FROM portfolio_ref.documents;
  IF visible_count <> 1 THEN
    RAISE EXCEPTION 'Tenant A did not see exactly its own row';
  END IF;

  UPDATE portfolio_ref.documents
  SET object_key = 'validation/tenant-a/updated'
  WHERE tenant_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  GET DIAGNOSTICS affected_count = ROW_COUNT;
  IF affected_count <> 1 THEN
    RAISE EXCEPTION 'Tenant A could not update its own row';
  END IF;

  UPDATE portfolio_ref.documents
  SET object_key = 'validation/tenant-b/changed'
  WHERE tenant_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
  GET DIAGNOSTICS affected_count = ROW_COUNT;
  IF affected_count <> 0 THEN
    RAISE EXCEPTION 'Tenant A updated Tenant B row';
  END IF;

  DELETE FROM portfolio_ref.documents
  WHERE tenant_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
  GET DIAGNOSTICS affected_count = ROW_COUNT;
  IF affected_count <> 0 THEN
    RAISE EXCEPTION 'Tenant A deleted Tenant B row';
  END IF;

  BEGIN
    INSERT INTO portfolio_ref.documents (tenant_id, id, object_key, sha256_digest)
    VALUES (
      'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
      '44444444-4444-4444-8444-444444444444',
      'validation/cross-tenant/original',
      'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd'
    );
    RAISE EXCEPTION 'Tenant A inserted a Tenant B row';
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;

  BEGIN
    UPDATE portfolio_ref.documents
    SET tenant_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    WHERE tenant_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
    RAISE EXCEPTION 'Tenant A changed row ownership to Tenant B';
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;
END
$validation$;

INSERT INTO portfolio_ref.documents (tenant_id, id, object_key, sha256_digest)
VALUES (
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  '55555555-5555-4555-8555-555555555555',
  'validation/tenant-a/allowed',
  'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
);

DO $validation$
DECLARE
  affected_count integer;
BEGIN
  DELETE FROM portfolio_ref.documents
  WHERE tenant_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    AND id = '55555555-5555-4555-8555-555555555555';
  GET DIAGNOSTICS affected_count = ROW_COUNT;
  IF affected_count <> 1 THEN
    RAISE EXCEPTION 'Tenant A could not delete its own row';
  END IF;
END
$validation$;

ROLLBACK TO SAVEPOINT tenant_a_transaction_scope;
RELEASE SAVEPOINT tenant_a_transaction_scope;

SAVEPOINT tenant_b_transaction_scope;
SET LOCAL portfolio_ref.tenant_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
DO $validation$
DECLARE
  visible_count integer;
  tenant_a_visible_count integer;
BEGIN
  SELECT count(*) INTO visible_count FROM portfolio_ref.documents;
  IF visible_count <> 1 THEN
    RAISE EXCEPTION 'Tenant B did not see exactly its own row';
  END IF;

  SELECT count(*) INTO tenant_a_visible_count
  FROM portfolio_ref.documents
  WHERE tenant_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  IF tenant_a_visible_count <> 0 THEN
    RAISE EXCEPTION 'Tenant B saw Tenant A rows on the reused session';
  END IF;
END
$validation$;
ROLLBACK TO SAVEPOINT tenant_b_transaction_scope;
RELEASE SAVEPOINT tenant_b_transaction_scope;

RESET ROLE;
ROLLBACK;

DO $validation$
DECLARE
  current_owner oid;
  current_acl aclitem[];
  current_schema_acl aclitem[];
  baseline_owner oid;
  baseline_acl aclitem[];
  baseline_schema_acl aclitem[];
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname IN (
      'portfolio_ref_rls_validation_owner',
      'portfolio_ref_rls_validation_runtime'
    )
  ) THEN
    RAISE EXCEPTION 'validation roles survived rollback';
  END IF;

  SELECT relowner, relacl
  INTO current_owner, current_acl
  FROM pg_class
  WHERE oid = to_regclass('portfolio_ref.documents');

  SELECT nspacl INTO current_schema_acl
  FROM pg_namespace
  WHERE oid = to_regnamespace('portfolio_ref');

  SELECT relowner, relacl, nspacl
  INTO baseline_owner, baseline_acl, baseline_schema_acl
  FROM portfolio_ref_rls_validation_baseline;

  IF current_owner IS DISTINCT FROM baseline_owner THEN
    RAISE EXCEPTION 'temporary table ownership survived rollback';
  END IF;
  IF current_acl IS DISTINCT FROM baseline_acl THEN
    RAISE EXCEPTION 'temporary table grants survived rollback';
  END IF;
  IF current_schema_acl IS DISTINCT FROM baseline_schema_acl THEN
    RAISE EXCEPTION 'temporary schema grants survived rollback';
  END IF;
END
$validation$;
