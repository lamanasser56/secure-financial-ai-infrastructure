# ADR-004: Bounded Google SDP redaction evaluation

**Status:** Accepted for evaluation only.

## Decision

Microsoft Presidio remains the authoritative redaction implementation and default trusted-runtime path. Its code and Kubernetes reference manifests remain in this repository. Presidio is required until a proposed replacement passes the complete evaluation, security review, qualification, and rollback requirements, followed by a separate decision and Change Set.

Google Sensitive Data Protection (Google SDP) is a candidate for a bounded, non-production, synthetic-text-only comparison with Presidio. It is disabled by default. This decision authorizes an evaluation plan, not an API call, implementation, deployment, automatic replacement, production readiness claim, or regulatory compliance claim. The [evaluation plan](../../security/google-sdp-evaluation-plan.md) defines evidence needed before any selection.

## Regional and data boundary

The candidate location is Dammam `me-central2`, using only the regional endpoint `dlp.me-central2.rep.googleapis.com`. A future adapter must take this endpoint from trusted deployment configuration, never from request data. Global endpoints, automatic global or cross-region fallback, silent endpoint substitution, and sending evaluation data to another region are prohibited. An unavailable or invalid regional endpoint must fail closed. The regional behavior still requires independent verification; naming an endpoint does not prove residency.

Only generated synthetic text may enter a future evaluation. Customer or production data, real financial records, tenant identifiers, national IDs, Iqama numbers, commercial-registration numbers, IBANs, phone numbers, invoices, documents, uploaded customer files, images sent to Google SDP, and production OCR content are prohibited. Synthetic text may represent OCR corruption; OCR itself remains upstream. This decision does not claim regional Google SDP image or OCR processing in Dammam.

## Identity and failure boundary

The intended future path is GKE Workload Identity → Google IAM → the Google SDP regional endpoint. This Change Set implements and authorizes neither the identity binding nor IAM access. Static Google service-account keys, embedded or Git-committed credentials, LiteLLM client or administrative keys, and application-managed provider secrets are prohibited for SDP authentication.

A future adapter must fail closed on missing configuration, wrong region, invalid endpoint, authentication or authorization failure, service unavailability, malformed response, incomplete required de-identification, or failed policy validation. Every such failure must produce **zero LiteLLM requests**. There is no automatic fallback from Google SDP to Presidio within the same runtime request. Offline comparison may use both candidates; runtime fallback is outside this decision. LiteLLM remains the sole provider gateway for any later approved path.

## Consequences

No Google SDP adapter, workload, credential, API call, or qualification evidence is created by this decision. Presidio remains available as the rollback path during any later integration. Passing a bounded evaluation can lead only to a further integration proposal; making Google SDP authoritative requires a separate ADR and Change Set.
