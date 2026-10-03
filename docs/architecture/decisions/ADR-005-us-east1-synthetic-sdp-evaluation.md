# ADR-005: us-east1 synthetic SDP evaluation amendment

**Status:** Accepted for preparation only. Execution approval pending for the exact revised commit and complete bundle.

## Context

The historical Dammam state-bucket create failed before Terraform initialization. Audit evidence granted bucket-create IAM; effective project location policy allows all locations. The owner reports a USA billing account. Its self-serve/invoiced type and Dammam entitlement are unconfirmed. No SDP API was tested. See [eligibility assessment](../../security/google-sdp-regional-eligibility.md).

## Decision

Supersede only [ADR-004](ADR-004-bounded-google-sdp-evaluation.md)'s regional selection with `us-east1` (South Carolina). This is a new bounded evaluation location, not a workaround for billing or purchase requirements. Do not change billing or pursue KSA/CNTXT onboarding. State storage, Artifact Registry and SDP use `us-east1`; the unchanged dedicated GKE root uses `us-east1-b`.

The closed [deployment artifact](../../../evaluation/google-sdp/deployment.json) selects `dlp.us-east1.rep.googleapis.com`. The adapter loads this trusted, image-bound file at startup, validates exact keys and values, and constructs `projects/PROJECT_ID/locations/us-east1` using trusted project identity. Requests, environment variables and alternate paths cannot select a region. Missing/invalid configuration, endpoint or provider failure fails closed. Global endpoints and automatic cross-region/provider fallback remain prohibited. Release, rendering, manifests and zero-SDP network preflight must agree with the same selection.

Presidio remains authoritative. Google SDP remains disabled and unwired to the trusted runtime. Only the unchanged nine-case synthetic corpus may enter a separately approved live evaluation. Maximum 18 SDK attempts, no application or Job retries, vulnerability policy with zero unapproved HIGH/CRITICAL, keyless identity, immutable registry digest and verified signature, genuine native datapath verdicts, owner-review limitations, USD 5 operator stop limit, six-hour cluster lifetime and cleanup beginning by hour four remain unchanged. No real data, production authorization, LiteLLM path or provider-authority change is permitted.

## Consequences and execution boundary

The image contents changed, requiring a new offline reproducible build, SBOM and scan/policy evidence; preserve historical Dammam evidence. The old approval at `2d1c87af7e17b4c7d45591c7479d02727c75cfc5` does not authorize new-region provisioning, push, publication, signing, deployment or calls. Review the complete amended source/resource/IAM/cost/cleanup bundle at one checkpoint. Reconfirm supported location metadata and account/API permissions through actual execution gates after approval; read-only checks cannot guarantee resource creation or API success.

No Saudi residency, independent review, SDP accuracy, production readiness, Presidio replacement or full CS6 completion is claimed. Native FQDN policy remains DNS-derived IP/port enforcement with shared-IP, Layer-7 and DNS-query limitations. Spending and cluster lifetime are operator-managed, with owner cleanup takeover required after disconnect.
