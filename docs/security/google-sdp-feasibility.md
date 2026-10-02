# Google Sensitive Data Protection feasibility

Research concluded conditional feasibility only. Google SDP has not been called, implemented, deployed, or qualified. Microsoft Presidio remains the authoritative redaction implementation and default runtime path. [ADR-004](../architecture/decisions/ADR-004-bounded-google-sdp-evaluation.md) permits only a bounded, non-production, synthetic-text evaluation; the [evaluation plan](google-sdp-evaluation-plan.md) defines its future evidence gates.

The candidate Dammam location is `me-central2`, with regional endpoint `dlp.me-central2.rep.googleapis.com`. Global and cross-region fallback are prohibited. A future adapter must fail closed if the regional endpoint is invalid or unavailable, with no LiteLLM request and no automatic Presidio fallback within that request. Keyless identity is only a future design; no Workload Identity binding or IAM permission is created here.

No Arabic, Saudi-identifier, OCR, image, or commercial-registration detection accuracy is proven. OCR processing remains upstream; only generated synthetic textual output may be considered. The research does not establish regional image/OCR processing, data residency, production readiness, or regulatory compliance. No Google API call, cloud resource, provider cutover, or production-data processing is represented by this document.
