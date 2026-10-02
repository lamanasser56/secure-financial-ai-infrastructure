# Phase 3B redaction contract

The trusted runtime calls a provider-neutral `RedactorClient.redact(text) → RedactionResult` boundary before LiteLLM. The result contains only redacted text and a tuple of normalized entity category names. The runtime does not receive raw spans, detected values, provider responses, credentials or endpoints. Its closed trace schema retains the existing Presidio stage names for failures.

The sole concrete implementation is [PresidioRedactor](../../runtime/phase3/adapters.py): Analyzer → validate analyzer response → Anonymizer → validate anonymizer response → provider-neutral result. Supported categories are closed in [trusted_runtime.py](../../runtime/phase3/trusted_runtime.py). Analyzer results must have valid, non-overlapping, in-bounds spans and bounded scores. Empty valid analysis still goes through Anonymizer. Protected fragments must be absent from the result, and empty redacted text is rejected. Malformed, timed-out or unavailable responses stop before LiteLLM. No automatic runtime fallback is authorized.

The [Presidio manifests](../../kubernetes/apps/presidio/) define two internal Services, separate ServiceAccounts, non-root workloads, probes and client-restricted NetworkPolicies. The analyzer configuration includes Saudi-specific synthetic detector patterns and an offline email validation override. The [synthetic cases](../../tests/phase3/presidio/synthetic-cases.json) are test data, not customer data.

Repository tests establish Python boundary behavior. Detector accuracy for Arabic, mixed script, OCR errors and production financial documents, plus live Presidio qualification, require separate evidence.

Provider neutrality is an internal contract boundary. It does not implement Google SDP, which remains evaluation-only under [ADR-004](../architecture/decisions/ADR-004-bounded-google-sdp-evaluation.md). Presidio remains authoritative and enabled. A future provider must return the same neutral result and fail closed; replacing Presidio needs a separate implementation, tests, qualification and ADR approval.
