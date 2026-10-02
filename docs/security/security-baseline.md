# Security baseline

1. Validate identity and derive tenant context from claims before authorization or tool routing. Deny on missing or malformed context.
2. Reject client-supplied tenant, model, provider, policy and approval decisions. Apply structured input and output validation.
3. Redact sensitive input before LiteLLM. Do not bypass Analyzer or Anonymizer on failure, timeout or empty valid analysis.
4. Restrict gateway and redaction Services to named clients and authenticate gateway requests. Default-deny networking remains in force; cloud egress requires a target-specific control beyond DNS labels.
5. Run containers non-root with minimal privileges, read-only root filesystems where supported, bounded resources and immutable reviewed image references.
6. Keep credentials outside Git and images. Separate runtime, migration, provider and signing identities. Scope, rotate and revoke each independently.
7. Emit only sanitized bounded audit and trace fields. Keep prompts, financial content, raw tenant IDs, tokens and exception text out of telemetry and CI artifacts.
8. Fail image promotion when required provenance, scan, SBOM, signature or policy evidence is missing. Old exception records are not reusable approvals.

The [threat model](threat-model.md) and [operations runbooks](../operations/README.md) expand these controls. Repository presence is not deployment evidence.
