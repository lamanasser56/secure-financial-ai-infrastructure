# Tenant authority and database isolation

Tenant identity comes from validated authentication claims. A server-side resolver creates immutable tenant context; request bodies, prompts, tool arguments, URLs and arbitrary headers are never authoritative. The runtime rejects tenant-shaped input recursively before reaching the gateway.

Database access needs a non-owner runtime role without `BYPASSRLS`, transaction-local tenant context, `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` on tenant-owned tables, and policies for each required command. Migration ownership and runtime access must use separate credentials. A pooled connection must not carry tenant context into the next transaction.

The [reference SQL](../../database/README.md) is a minimal, synthetic illustration and is not the private team's authoritative product schema. Real table classifications, roles, grants, migrations and connection-pool behavior require application-owned integration and disposable-database negative tests.
