# ADR-001: Single provider gateway

**Status:** Accepted for this reference architecture. **Provenance:** sanitized adaptation of the source project's provider-gateway decisions.

All provider-bound AI requests pass through the trusted runtime, Presidio and LiteLLM. A deployment chooses one approved provider model and a keyless workload identity where supported. The application receives a scoped gateway credential, never a cloud provider credential or the LiteLLM administrative master key. No direct-provider route or fallback is allowed.

The repository leaves the provider project, model, region, identity binding and credential delivery unresolved. Their absence prevents live use rather than selecting an unsafe default.
