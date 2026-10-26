# Current-source disposable assessment procedure (draft)

This procedure is **not executable yet**. PR #170 remains draft until all twelve
current-source probes, their guard and cleanup integration, and offline checks
are complete. The historical operator scripts are read-only behavioral reference;
no runtime step imports them or depends on their location.

The assessed source is the final frozen commit S and its seven-image lock.
Render with live_session.py into a private directory outside the checkout.
The release lock must identify S exactly. The operator verifies source image
signatures, KMS attestations and provenance, copies the seven exact digests to
the disposable registry, signs/verifies disposable attestations, and checks
running Pod image IDs before the first case. The provider route is a fixed
in-cluster stub and the gateway has no Workload Identity in this bundle.

| Sequence | Current repository source | Private evidence |
| --- | --- | --- |
| Prepare | live_session.py, render_live_bundle.py, stage_live_bundle.py | Run manifest, bundle and seven ordered stage hashes |
| Independent cleanup first | operator_setup.py, operator_janitor.py, .github/workflows/assessment-janitor.yml, janitor.py | Labelled disposable project, independent watch receipt, deadline and cleanup fallback |
| Create and qualify | operator_cluster.py, operator_images.py, operator_admission.py | Create-only Terraform plan, seven exact copies, cryptographic admission receipts |
| Apply | operator_apply.py, live_case_guard.py | Applied object count, running image digests, both zeroed durable ledgers |
| Cases | live_case_runner.py, live_probe_*.py | Before/after durable ledgers and boolean-only case receipt; stop on any failure |
| Cleanup | operator_cleanup.py, janitor.py | Destroy-only Terraform plan, absence inventory, billing unlink and deletion request |

The case order is D02, D06, D04, D05, D07, O03, O04, K01, K02, K03, K05,
R01. The setup reserve is 2 completed redactions / 4 SDK attempts; D02 may
use 4 / 10 and R01 2 / 5; other cases may use zero. Planned total is 8 / 19,
manual stop 12 / 40, hard ceiling 20 / 60. Only synthetic data may be used;
no external LLM calls are allowed. The independent janitor must remain active
before each case, and the run has a 180-minute deadline and $50 cost ceiling.
Every case reads both durable ledgers immediately before and after its probe.

The current code has probes for D02, D04-D07, O04, K01-K03, K05 and R01.
O03 and final command binding are outstanding. K03 still needs its restricted
Pod Security Admission check. D04's live portion tests wrong worker key,
unexpected user field, worker secret inventory and direct database denial.
An active cross-user capability is covered by the current-source integration
test in platform/core/tests/test_trusted_boundaries.py; the production
frontdoor does not expose active capabilities for a live replay, so a revoked
token must never be reported as live proof of cross-user binding.

Private manifests, passwords, kubeconfig, raw requests and case details stay
outside Git. Receipts contain counters, digests and booleans only. Any failed
security check, unreadable ledger, lost janitor, deadline or ceiling stops the
run; cleanup remains mandatory and a PASS requires resource absence, billing
unlink and a confirmed project deletion request.
