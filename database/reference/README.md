# Reference-only tenant/RLS fixture

These SQL files were adapted from the author's MASAR AI Infrastructure database foundation. They use only synthetic tenants and document metadata. They are **not** an active product migration and do not reproduce the product schema or Phase 5 product-table evidence.

Run against a newly created disposable PostgreSQL database named `portfolio_rls_test` with an administrative test role:

```bash
export PORTFOLIO_TEST_DATABASE_URL='postgresql://.../portfolio_rls_test'
bash scripts/test-reference-rls.sh
```

The schema migrations are forward-only and non-idempotent. The test runner requires the exact database name and resets only its `portfolio_ref` schema before each run, so this database must be disposable. The behavioral script creates synthetic roles and rows inside rolled-back transactions. A successful disposable test proves this fixture's controls, not another database's isolation or deployment state.

- `migrations/001_tenant_schema.sql`: tenant directory and tenant-owned document metadata.
- `migrations/002_documents_rls.sql`: `ENABLE`/`FORCE` RLS with command-specific policies.
- `tests/001_tenant_schema_checks.sql`: schema and tenant-key structure.
- `tests/002_documents_rls_checks.sql`: catalog-level policy and flag checks.
- `tests/002_documents_rls_behavior.sql`: missing/malformed/cross-tenant context, owner and runtime-role enforcement, and transaction-local reset.
