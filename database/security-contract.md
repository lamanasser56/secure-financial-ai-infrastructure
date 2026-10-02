# Portable database security contract

The original Phase 5 work hardened a product-owned PostgreSQL schema. The product tables and backend implementation remain in the team repository. This document extracts the security rules without asserting ownership of those tables.

1. Migration credentials own schema changes; runtime credentials are non-owner, non-superuser and `NOBYPASSRLS`. A runtime session cannot assume a migration identity.
2. Tenant-owned tables enable and force RLS. Policies cover the required `SELECT`, `INSERT`, `UPDATE` and `DELETE` behavior and reject missing, blank, malformed and conflicting tenant context.
3. The application derives tenant context from authenticated membership and sets it transaction-locally. A pooled connection must clear it at commit or rollback before reuse.
4. Global authentication-control tables require narrow column grants and controlled functions rather than a false claim of tenant RLS. Pre-auth token lookup uses only a hash-bound, time-limited context and cannot become broad table access.
5. Tenant foreign keys and import-batch relationships must prevent cross-tenant references even when an operation's individual rows satisfy RLS.
6. Qualification uses disposable roles, separate migrator and runtime logins, negative cross-tenant tests, owner/FORCE-RLS tests, and explicit catalog inspection. Local test results do not prove a live production database.

The synthetic [reference fixture](reference/README.md) covers the core RLS mechanism. Product-specific invitation, auth-data and import-batch controls need a new product integration suite; the original SQL and backend tests are deliberately not copied here.
