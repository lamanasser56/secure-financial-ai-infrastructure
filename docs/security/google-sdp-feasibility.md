# Google Sensitive Data Protection feasibility

## Historical research: Dammam selection superseded

This initial research described conditional feasibility at Dammam `me-central2`, using `dlp.me-central2.rep.googleapis.com`. It did not authorize calls, implementation, deployment or authority changes. [ADR-004](../architecture/decisions/ADR-004-bounded-google-sdp-evaluation.md) preserves that historical decision. The later Storage bootstrap failed with a location-related 403; this was not an SDP test or denial.

## Current synthetic-only preparation

[ADR-005](../architecture/decisions/ADR-005-us-east1-synthetic-sdp-evaluation.md) and the [evaluation plan](google-sdp-evaluation-plan.md) now prepare `us-east1` for a USA billing account, without changing billing or pursuing KSA/CNTXT onboarding. The disabled adapter and offline harness are implemented; image qualification is local evidence only. Registry publication, signing, GKE execution, identity bindings and live SDP remain unproven. Presidio remains authoritative.

No Arabic, Saudi-identifier, OCR, image, commercial-registration or real-world detection accuracy is proven. Only generated text is authorized for preparation. No Saudi residency, production readiness, compliance, full CS6 completion, real-data authorization, automatic fallback or Presidio replacement follows. The complete revised execution bundle requires one explicit owner approval.
