# PostgreSQL security work

The [reference fixture](reference/README.md) is an adapted, synthetic version of the author's original two-table RLS foundation. It demonstrates tenant-directory authority, command-specific policies, `FORCE ROW LEVEL SECURITY`, transaction-local context and negative cross-tenant behavior. **It is reference-only and is not the private team's authoritative product schema.** It must not be applied as a product migration.

The [security contract](security-contract.md) records the portable principles from later user-authored Phase 5 hardening without copying teammate-owned tables, backend services or the product migration history. Real roles, grants, connection pools and table policies remain integration-dependent.
