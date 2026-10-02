# Security qualification boundaries

The portable suite should prove that authentication, tenant context, authorization, schema validation, policy, redaction and approval failures stop before a provider or tool executor. It should reject tenant-shaped input at any depth, invalid tool IDs, malformed outputs, changed approval arguments, missing audit schemas and hostile error identifiers. No raw protected value may appear in traces or audit events.

The source project also qualified product RLS over an authoritative team-owned schema. That evidence cannot be lifted unchanged: a standalone fixture can prove the RLS mechanism, role separation and pooled-context clearing, but not the original product's 18-table inventory or its deployment state. The [tenant architecture](../architecture/tenant-architecture.md) distinguishes the two claims.

Container image qualification remains separate from source tests. Candidate recipes and policy validators can be checked locally, but an image must be built, scanned, inventoried, signed and validated in its target environment before promotion.
