BEGIN TRANSACTION READ ONLY;

WITH checks (check_name, passed) AS (
  VALUES
    (
      'portfolio_ref schema exists',
      to_regnamespace('portfolio_ref') IS NOT NULL
    ),
    (
      'tenant directory exists',
      to_regclass('portfolio_ref.tenants') IS NOT NULL
    ),
    (
      'documents table exists',
      to_regclass('portfolio_ref.documents') IS NOT NULL
    ),
    (
      'tenant directory is classified as platform control data',
      obj_description(to_regclass('portfolio_ref.tenants'), 'pg_class')
        LIKE 'Platform control data:%'
    ),
    (
      'documents table is classified as tenant-owned',
      obj_description(to_regclass('portfolio_ref.documents'), 'pg_class')
        LIKE 'Tenant-owned:%'
    ),
    (
      'documents tenant_id is non-null',
      EXISTS (
        SELECT 1
        FROM pg_attribute
        WHERE attrelid = to_regclass('portfolio_ref.documents')
          AND attname = 'tenant_id'
          AND attnotnull
          AND NOT attisdropped
      )
    ),
    (
      'documents primary key is tenant scoped',
      EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = to_regclass('portfolio_ref.documents')
          AND conname = 'documents_pkey'
          AND contype = 'p'
          AND pg_get_constraintdef(oid) = 'PRIMARY KEY (tenant_id, id)'
      )
    ),
    (
      'document object reference uniqueness is tenant scoped',
      EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = to_regclass('portfolio_ref.documents')
          AND conname = 'documents_tenant_object_key_key'
          AND contype = 'u'
          AND pg_get_constraintdef(oid) = 'UNIQUE (tenant_id, object_key)'
      )
    ),
    (
      'documents tenant foreign key targets tenant directory',
      EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = to_regclass('portfolio_ref.documents')
          AND confrelid = to_regclass('portfolio_ref.tenants')
          AND conname = 'documents_tenant_fkey'
          AND contype = 'f'
      )
    ),
    (
      'document SHA-256 format constraint exists',
      EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = to_regclass('portfolio_ref.documents')
          AND conname = 'documents_sha256_digest_format'
          AND contype = 'c'
      )
    )
)
SELECT check_name, passed
FROM checks
ORDER BY check_name;

ROLLBACK;
