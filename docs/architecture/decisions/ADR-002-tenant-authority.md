# ADR-002: Trusted tenant authority

**Status:** Accepted for the reference runtime.

Authentication claims are the only input to tenant resolution. Tool metadata declares required actions; clients cannot provide authorization decisions. Tenant-owned database rows require transaction-local context and enforced RLS. Missing, malformed, stale or conflicting context fails closed.

The [Phase 3 runtime](../../../runtime/phase3/trusted_runtime.py) and [Phase 4 invocation boundary](../../../runtime/phase4/tool_invocation.py) implement repository-level checks. A real authenticator, authorizer, connection pool and product schema remain integration-dependent.
