# Partial SDP agent preparation inputs

**Offline only; full campaign BLOCKED.** The 42 safe fixtures do not replace the
proposed 87-case eight-class campaign. Five classes and 45 cases lack verified
provenance. Google detection quality is unmeasured. See the
[coverage matrix](../../docs/security/google-sdp-agent-coverage.md).

- [Fixture schema](offline-fixtures.schema.json) separates raw synthetic inputs
  from sanitized case/count summaries.
- [Acceptance](acceptance.json) freezes zero misses, false positives and leakage
  per required class/language, preservation of mandatory negatives and no credit
  for refusal or absent coverage.
- The [offline inventory](../../scripts/inspect-sdp-qualification-preparation.py)
  validates preparation without constructing a client or replaying labels as a
  detector. No live option exists.

The candidate image retains the historical nine-case seed harness. It tests the
changed candidate boundary; it is not a full-campaign image. A later frozen corpus,
eight-class detector configuration, live span scorer and matching release/deployment
contracts require separate qualification before an execution checkpoint.

Keep source fixtures in this directory. Do not log raw text, expected coordinates,
provider quotes or raw outputs. Retain sanitized summaries and file-level provenance
hashes privately. No image signature is inherited from the old signed seed image.
