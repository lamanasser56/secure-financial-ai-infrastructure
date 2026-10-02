BEGIN;

CREATE SCHEMA portfolio_ref;

COMMENT ON SCHEMA portfolio_ref IS
  'PORTFOLIO_REF application schema; access and RLS are configured by later approved changes.';

CREATE TABLE portfolio_ref.tenants (
  id uuid NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT tenants_pkey PRIMARY KEY (id)
);

COMMENT ON TABLE portfolio_ref.tenants IS
  'Platform control data: authoritative internal tenant directory.';
COMMENT ON COLUMN portfolio_ref.tenants.id IS
  'Internal UUID supplied by the trusted integration layer.';

CREATE TABLE portfolio_ref.documents (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL,
  object_key text NOT NULL,
  sha256_digest text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT documents_pkey PRIMARY KEY (tenant_id, id),
  CONSTRAINT documents_tenant_object_key_key UNIQUE (tenant_id, object_key),
  CONSTRAINT documents_tenant_fkey
    FOREIGN KEY (tenant_id)
    REFERENCES portfolio_ref.tenants (id),
  CONSTRAINT documents_object_key_not_blank
    CHECK (object_key = btrim(object_key) AND object_key <> ''),
  CONSTRAINT documents_sha256_digest_format
    CHECK (sha256_digest ~ '^[0-9a-f]{64}$')
);

COMMENT ON TABLE portfolio_ref.documents IS
  'Tenant-owned: metadata and integrity reference for an immutable original document.';
COMMENT ON COLUMN portfolio_ref.documents.tenant_id IS
  'Authoritative tenant UUID supplied through the trusted integration path.';
COMMENT ON COLUMN portfolio_ref.documents.id IS
  'Document UUID supplied by the trusted integration layer.';
COMMENT ON COLUMN portfolio_ref.documents.object_key IS
  'Tenant-scoped reference to the immutable original in future Object Storage.';
COMMENT ON COLUMN portfolio_ref.documents.sha256_digest IS
  'Lowercase hexadecimal SHA-256 digest calculated from the original uploaded bytes.';

COMMIT;
