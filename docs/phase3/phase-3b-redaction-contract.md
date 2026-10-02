# Phase 3B redaction contract

The trusted runtime calls Presidio Analyzer and Anonymizer before LiteLLM. Supported categories are closed in [trusted_runtime.py](../../runtime/phase3/trusted_runtime.py). Analyzer results must have valid, non-overlapping, in-bounds spans and bounded scores. Empty valid analysis still goes through Anonymizer. The original fragments represented by spans must be absent from transformed text. Malformed, timed-out or unavailable responses stop before the gateway.

The [Presidio manifests](../../kubernetes/apps/presidio/) define two internal Services, separate ServiceAccounts, non-root workloads, probes and client-restricted NetworkPolicies. The analyzer configuration includes Saudi-specific synthetic detector patterns and an offline email validation override. The [synthetic cases](../../tests/phase3/presidio/synthetic-cases.json) are test data, not customer data.

Repository tests establish Python boundary behavior. Detector accuracy for Arabic, mixed script, OCR errors and production financial documents, plus live Presidio qualification, require separate evidence.
