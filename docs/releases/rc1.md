# Agent Runtime Platform: RC1 source preparation

Infrastructure · Security · Operations

This is an educational source candidate. No release tag has been created, no images have been built or signed, and no deployment or independent live assessment is claimed for these changes.

## Scope

Local corrections cover numeric representation checks, SAR major-unit validation, explicit quotation of untrusted stored notes, malformed model/tool responses with turn audit records, malformed authentication input and Ops verification of the approved object and desired state. Exact whole-note quotation is required for notes containing unsupported business-state words. Numeric checks remain bounded syntactic checks, not a complete semantic verifier for arbitrary financial prose.

The Financial Agent is an example workload; it is not the product identity. The Security & Operations Agent is an example of operational automation with application-level approval checks. A compromised executor can still bypass those checks through its Kubernetes token. Independent resource-boundary approval enforcement remains open.

## Earlier preparation scope and continued migration

The earlier source stage left these architecture gaps open; the continued [trusted-boundary migration](rc1-boundary-migration.md) prepares separate services and identity contracts. Its live verification and qualified artifacts remain pending. In the historical runtime, client-side redaction does not constrain hostile agent code. RLS relies on caller-selected user/tenant settings and shared data roles. Ops admission constrains mutation shape but does not independently verify owner approval. These are open architecture findings, not accepted risks or fixes in this candidate.

The forty-case isolated live assessment is still not executed. Offline tests use scripted models, redactor/DB fixtures and a fake Kubernetes client. They cannot prove CNI, GKE admission, Workload Identity, real RLS behavior, cloud DLP accuracy, real model behavior, restoration or service fairness. No real LLM or SDP requests are part of this source validation.

## Release impact

Modified application source requires distinct future Financial/app/Ops images with new digests, scans, SBOMs, signatures and attestations. The redactor's mounted Python program also changes: its external file hash and generated ConfigMap name must be recorded and rolled out together. It is outside the historical image signature. SDP policy/corpus hashes, runtime paths, original image pins and historical qualification bytes remain unchanged.

This document is an input to the Guide's build-time docs index. A future Guide build would therefore be a distinct artifact too. The existing Guide index remains unchanged. README branding does not rename resource, repository, package, image, IAM or Terraform identities.

## Candidate proposal

Proposed tag: `v0.1.0-rc.1` (not created). Proposed changelog: stronger Financial output checks and failure audit; bounded malformed authentication rejection; Ops postcondition binding; platform-focused portfolio identity. Integration must follow cleanup/conflict review and independent security review. The candidate is not ready for a security release until its declared blockers and validation gaps are resolved or explicitly accepted by the owner.
