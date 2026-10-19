# Security documentation

- [Baseline](security-baseline.md): identity, least privilege, fail-closed and telemetry rules.
- [Threat model](threat-model.md): trust-boundary threats and controls.
- [Key ownership](kms-ownership.md): credential and key lifecycle.
- [Container release policy](container-vulnerability-release-policy.md): scanning, exception and promotion rules.
- [Google SDP feasibility](google-sdp-feasibility.md): a research-only candidate; Presidio remains authoritative.
- [Google SDP evaluation plan](google-sdp-evaluation-plan.md): synthetic-text comparison and evidence gates under [ADR-004](../architecture/decisions/ADR-004-bounded-google-sdp-evaluation.md).
- [Claims inventory](claims-inventory.md): every security claim, its control, the test that proves it, and whether the test input is realistic and on the real end-to-end path.
- [Realistic-data review (October 2026)](realistic-data-review-2026-10.md): findings from the synthetic Saudi/bilingual corpus, each with its fix PR.
- [Realistic-data corpus](realistic-data-corpus.md): what the synthetic corpus contains, its rules (never real people), and where it is used.

No source-project image-specific risk acceptance record is active here. A clean scanner result is point-in-time evidence, not proof of no vulnerability.
