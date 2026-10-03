# ADR: bounded read-only demo agents

## Status

Accepted for the separately authorized offline agent/UI implementation after completion and cleanup of the synthetic SDP milestone. This decision changes no redactor authority, provider credentials or evaluation scope.

## Decision

Compose the canonical Phase 3 runtime and Phase 4 tool-governance contracts in a reusable coordinator. Add five read-only tools as a registry instance with exact schema bindings, separate financial/diagnostics policies, synthetic fixture sources, CLI entry points and a loopback-only private UI.

Use deterministic model responses and simulated startup identities for the initial demonstration. Keep truthful `provider_called=false` traces through an explicit trusted runtime simulation option; existing live behavior remains the default. Reuse `PresidioRedactor` with labelled synthetic service doubles. A failed redaction operation blocks the run. Preserve the existing output envelope by embedding a closed decision JSON object in its summary string.

Require independent input/output validation, authorization, capability confinement, prompt-injection assessment, complete tool governance, minimization, redaction and finite budgets. Model output cannot execute shell commands, select arbitrary sources, change tenants or adjust provider configuration. Repairs remain suggestions. All financial calculations remain deterministic handler results.

## Consequences

The demonstration is runnable without secrets or live providers and reuses the repository's security interfaces. It is not real authentication or production language/model qualification. POSIX/main-thread deadlines constrain execution architecture; the initial UI is single-thread and private. In-memory audit traces need a durable integration before deployment. A separate live integration must qualify real identity, Presidio, LiteLLM client-key restrictions and gateway-owned Gemini/Vertex credentials. Google SDP remains disabled/unwired; Presidio remains authoritative.

See [architecture](architecture.md) and [live prerequisites](live-integration.md).
