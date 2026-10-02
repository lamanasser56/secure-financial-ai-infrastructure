# Phase 4A tool registry contract

The [registry schema](../../contracts/phase4/tool-registry.schema.json) contains versioned metadata for each tool. A tool declares its ID, owner, enabled flag, risk class, operation type, input/output schema references, required authorization action, approval requirement, audit class, source system and execution bounds. [Runtime validation](../../runtime/phase4/tool_registry.py) rejects unknown or disabled tools, malformed metadata, unsupported risk classes, missing authorization, and deferred schemas with sanitized categories.

Risk classes distinguish low-risk reads, sensitive financial reads, reversible writes and irreversible high-impact writes. A read is not assumed harmless. Both write tiers require approval. Schema references can remain deferred but a deferred schema prevents resolution. Tenant identity is never a tool argument or registry field; it comes from authenticated claims through the trusted runtime.

Registry resolution is structural readiness, not an execution grant. The [synthetic registry](../../tests/phase4/registry/sample-registry.json) contains illustrations rather than an authoritative product tool list. Any real tool needs application-owned authorization, input/output validators, policy, approval if required, and audit integration.
