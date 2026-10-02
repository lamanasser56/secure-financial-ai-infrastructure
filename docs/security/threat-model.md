# Threat model

| Threat | Boundary | Required control | Current evidence |
| --- | --- | --- | --- |
| Cross-tenant disclosure | Request → runtime → database | Claim-derived tenant, action authorization, FORCE RLS, transaction-local context | Runtime and synthetic SQL tests; product integration pending |
| Prompt or tool injection | Untrusted content → tool governance | Assessment, allowlist, schema validation, policy and approval | Repository tests; product executor pending |
| Direct provider bypass | Application → provider | One LiteLLM route after redaction, no fallback | Reference code and network templates; live integration pending |
| Protected content in telemetry | Runtime → logs/traces/audit | Closed schemas, bounded categories, no raw values | Repository tests; durable sinks pending |
| Secret theft | Git, Pods, cloud identity | External delivery, separate identities, minimal RBAC | Sanitized templates; cloud binding pending |
| Supply-chain compromise | Source → image → deployment | Pinned actions/tools, complete scans and SBOM, verified signature and provenance | Local qualification; deployment admission pending |
| Recovery failure | Cluster/database/storage | Owner-defined RPO/RTO, isolated backups, restore drill | Design only |

Residual risks include public HTTPS gateway egress, target-CNI differences, detector accuracy, provider data handling, identity configuration, alert delivery and application-owned authorization. These require target-environment tests; no repository-only result closes them.
