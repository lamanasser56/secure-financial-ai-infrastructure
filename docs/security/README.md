# Security documentation

Current platform:

- [Threat model](threat-model.md): threats, controls and their live status.
- [Claims inventory](claims-inventory.md): every security claim, its control, the test that proves it, and whether the test input is realistic and on the real end-to-end path.
- [Known limitations](known-limitations.md): accepted gaps, each with what would close it.
- [Security review (13 October 2026)](security-review-2026-10-13.md) and the [`main` branch protection](main-branch-protection.md).
- [Realistic-data review (October 2026)](realistic-data-review-2026-10.md): findings from the synthetic Saudi/bilingual corpus, each with its fix PR.
- [Realistic-data corpus](realistic-data-corpus.md): what the synthetic corpus contains, its rules (never real people), and where it is used.
- [Container release policy](container-vulnerability-release-policy.md): scanning, exception and promotion rules.
- [Binary Authorization attestor key](../agent-platform/kms-attestor.md): ownership and rotation.

History (earlier phases, kept as a record):

- [Baseline](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/security/security-baseline.md) and [key ownership](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/security/kms-ownership.md) from the reference design.
- [Google SDP feasibility](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/security/google-sdp-feasibility.md), the [evaluation plan](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/security/google-sdp-evaluation-plan.md) under [ADR-004](../architecture/decisions/ADR-004-bounded-google-sdp-evaluation.md), and the other `google-sdp-*` records. Sensitive Data Protection, not Presidio, is the redactor of the running platform.

No source-project image-specific risk acceptance record is active here. A clean scanner result is point-in-time evidence, not proof of no vulnerability.
