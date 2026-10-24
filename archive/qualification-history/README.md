# Qualification history (C windows, W4–W18)

## Exact historical Python locks — not current live qualification

`locks/` retains byte-for-byte copies of the three dependency locks named by
the historical qualification records. The files were recovered from Git blob
history and are used only by tests that verify those immutable records:

| Archived lock | SHA-256 of qualified bytes |
| --- | --- |
| `requirements-agent-composition.txt` | `0f8138170f4db09c943a591d814a5584eb7ab1ae80858981d8606da54a086cd9` |
| `requirements-google-sdp-runtime.txt` | `c232eac3a105050d5406a7cc80f5aa276c4fbbed52f3e8d5ff7892c548199a29` |
| `requirements-litellm-candidate.txt` | `71f9c84c122b3ee9ebac6fb00901f5730d888ed3e81c86bbb10d76f3c50c8d0a` |

**The current root locks are NOT live-qualified yet.** The [RC1 handoff](https://github.com/lamanasser56/secure-financial-ai-infrastructure/blob/bed7b0e/CLAUDE_HANDOFF_FINAL.md)
requires fresh live qualification for changed App/Ops/external files before any
qualification claim. Historical record hashes and operational gates remain
unchanged; operational gates continue to reject the changed current locks.
The regression test `test_current_locks_are_not_live_qualified_per_claude_handoff_final`
checks this distinction explicitly. Never install these archived files as
current runtime dependencies.

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
