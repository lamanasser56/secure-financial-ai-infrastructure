# Unwired context-pattern candidate

See the [policy matrix](../../docs/security/google-sdp-context-policy.md),
[ADR-007](../../docs/architecture/decisions/ADR-007-context-pattern-redaction-candidate.md)
and [current campaign proposal](../../docs/security/google-sdp-context-campaign-execution-bundle.md).
`policy.json` fixes eleven infoTypes mapped to eight neutral categories; the corpus
freezes 86 synthetic texts with exact expected value spans. No user upload or
request-selected detector, endpoint, project or credential is accepted.

Default command, in the existing locked worker SDK environment:

```bash
python scripts/evaluate-sdp-context-policy.py
```

This runs a Python reference only, with zero SDP calls. The sanitized offline report
is not Google's accuracy evidence. Live mode needs `--live` and the distinct trusted
`PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK` acknowledgement. Those controls do not
constitute approval. No live call is authorized by this preparation.

The fresh `campaign-qualification.json` record binds image inputs, matching Docker archives,
configuration digest, scan/SBOM/KEV/policy hashes and offline results. Configuration
digest is not a registry manifest or signature. The original signed seed image and
historical full 87-case qualification artifacts remain separate and unchanged.
No Presidio runtime selection, dependency lock or existing UI was changed.

## Current campaign preparation

The successful context-001 diagnostic establishes first-case compatibility only;
its original historical failure cause remains UNKNOWN. The policy and 86-case
corpus remain frozen: 70 mandatory cases and 16 unsupported observations.
New scoped results separate operational failures and unsupported observation
failures from mandatory acceptance. All failures stop without retries. The
[current proposal](../../docs/security/google-sdp-context-campaign-execution-bundle.md)
records the amended cost boundary, two-hour lifetime, minute-90 cleanup and exact
subsequent integration gates. It requires a new approval before publication or
execution. Original `qualification.json`, `diagnostic-qualification.json` and
historical offline results are preserved as separate immutable evidence.
