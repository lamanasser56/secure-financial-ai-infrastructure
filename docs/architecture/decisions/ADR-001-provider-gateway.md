# ADR-001: Single provider gateway

**Status:** Accepted for this reference architecture. **Provenance:** sanitized adaptation of the source project's provider-gateway decisions.

All provider-bound AI requests pass through the trusted runtime, Presidio and LiteLLM. A deployment chooses one approved provider model and a keyless workload identity where supported. The LiteLLM server alone receives the administrative `PORTFOLIO_LITELLM_MASTER_KEY`; the trusted runtime uses a separately issued, scoped `PORTFOLIO_LITELLM_CLIENT_KEY`. Runtime clients never receive the master key or a cloud provider credential. The runtime's `PORTFOLIO_LITELLM_BASE_URL` comes from trusted startup configuration and cannot be chosen by a request. No direct-provider route or fallback is allowed.

The operator must provision the client key with access limited to `secure-financial-chat` and appropriate budget and rate policy, then rotate and revoke it independently of the master key. This repository does not implement live key issuance or production rotation. The provider project, model, region, identity binding and credential delivery remain unresolved. No secret value belongs in Git; missing configuration prevents live use rather than selecting an unsafe default.
