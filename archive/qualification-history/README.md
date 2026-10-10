# Qualification history (C windows, W4–W18)

Engineering history, out of the platform path. Nothing here is built, deployed or tested by `make`.

**Honest record of C** (source 91d7e8c7):
- All 9 pre-channel C stages passed live in four windows (w13, w14, w15, w18): render, base, egress, secrets, database,
  bootstrap-database, quarantine, services, clients.
- The post-channel chain (channel verify → denials → compose → worker qualify → close) never completed. The causes were operator tunnels and Cloud
  Shell: w13 phase expiry, w14 check defect, w15 interrupted tunnel, w18 tunnels never ready, then the Cloud Shell weekly quota.
- **C did not pass.** It is superseded by the Phase E acceptance tests and attack suite
  ([ADR-008](../../docs/architecture/decisions/ADR-008-persistent-agent-platform.md)).

What moves here during the final week (Nov 3–7), sanitized:
- **Window tooling:** runners, transports, installers, verifiers, rebind tools, with their tests.
- **Receipts:** summaries only, no project-private values, keys or tokens.
- **The window timeline** (handoff excerpts).

Sanitization rule: no project number or ID, no service-account emails, no IPs, no secret material, no raw provider
output. Hashes of evidence are kept so the history stays verifiable against the retained private copies.

## Historical identifier note
Commits up to `91d7e8c7` (the qualified C source, kept unchanged to preserve the provenance chain: program manifest,
owner signatures and the C record) contain the evaluation project's GCP project identifier in one test
(`tests/phase3/runtime/test_composite_email_campaign.py`). A project identifier is not a credential: access requires
IAM permissions that it does not grant. The current tree uses a synthetic placeholder and passes `scripts/validate.py`.
The project and everything billable in it are torn down by 2026-11-08 (see `docs/agent-platform/teardown-plan.md`).
