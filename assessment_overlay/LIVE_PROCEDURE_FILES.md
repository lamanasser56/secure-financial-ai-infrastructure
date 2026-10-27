# Current-source disposable assessment procedure

The twelve current-source probes are bound by `live_case_runner.py`. The
historical operator scripts are read-only behavioral reference;
no runtime step imports them or depends on their location.

The assessed source is the final frozen commit S and its seven-image lock.
Render with live_session.py into a private directory outside the checkout.
The release lock must identify S exactly. Everything outside
`assessment_overlay/` must equal S, except the release lock and
`docs/evidence/`. So must every overlay file whose output is applied to the
assessment cluster (`source_selection.DEPLOYED_CONTENT`: the renderer, the
stager, the gateway/ops/redactor patches and the embedded provider stub,
redactor server, ops server, seed and SDP guard), and the bundle is rendered by
S's own renderer from a temporary detached worktree at S. Only orchestration,
waiting, verification and evidence code may change after S, and only in
commits: an uncommitted, untracked or hidden change anywhere refuses the
session. The private manifest records the harness
commit, its changed files and the digest of the S..HEAD `assessment_overlay/`
diff, which is kept as `evidence/harness.diff`; every later operator step
refuses a checkout whose HEAD or working tree changed since the session (cleanup
never does). The operator verifies source image
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

O03 sends a signed approval to the independent executor for a zero-replica,
disposable `fault-demo` Deployment after UID and resourceVersion changes. It
checks exact `TARGET_REPLACED` and `OBJECT_CHANGED` denials and unchanged spec
and image digest. K03 checks restricted Pod Security Admission with a
server-side dry run, separately from the executor's projected-token RBAC.
D04's live portion tests wrong worker key,
unexpected user field, worker secret inventory and direct database denial.
An active cross-user capability is covered by the current-source integration
test in platform/core/tests/test_trusted_boundaries.py; the production
frontdoor does not expose active capabilities for a live replay, so a revoked
token must never be reported as live proof of cross-user binding.

Every long-running or eventually consistent cloud step waits for its
observable result, bounded by the 180-minute deadline (`cloud_wait.py`): the
project create (owned only through its run label), billing link, the service
enable operation and then the enabled state, the default network removal,
janitor IAM and Workload Identity propagation (inside its watch step the
janitor retries its identity check for at most 15 minutes and otherwise fails
its job visibly; before the first case the runner waits until that window has
passed and requires the janitor still in its watch step, or cleans up),
Terraform applies (re-planned
create-only against the private state, at most three attempts), image copies,
disposable attestations and the first API server contact and stage applies.
Terraform runs from a private copy of the tracked root and module whose only
addition is a `backend_override.tf` for private local state. Cleanup deletes the
run's namespaces so their disks are released before the destroy, then polls the
absence inventory to zero; it is never bounded by the deadline.

Private manifests, passwords, kubeconfig, raw requests and case details stay
outside Git. Receipts contain counters, digests and booleans only. Any failed
security check, unreadable ledger, lost janitor, deadline or ceiling stops the
run; cleanup remains mandatory and a PASS requires resource absence, billing
unlink and a confirmed project deletion request.

Run this only after final release S/R evidence and the original deployment's
readiness pass. All commands below run from the repository root in an
ephemeral cloud operator environment with Python 3.12, the pinned repository
tools, authenticated operator identity, and `GH_TOKEN` scoped to workflow
dispatch/read. The private `ASSESSMENT_RUN_DIR` must be outside the checkout.
Values for project, registry, billing account and GKE version are supplied
privately; never print them in transcripts or evidence. No command here is
authorized during code/offline testing.

```bash
make tools operator-env
bash scripts/install-assessment-crane.sh "$PWD/.cache/platform-tools"
bash scripts/install-qualification-tools.sh "$PWD/.cache/platform-tools"
export PATH="$PWD/.cache/platform-tools:$PATH"
PYTHONPATH=assessment_overlay:platform/core/src:. .cache/operator-venv/bin/python -B assessment_overlay/live_session.py --images-lock platform/clouds/gke/release-rc1.lock.json --output "$ASSESSMENT_RUN_DIR" --kubectl .cache/platform-tools/kubectl
PYTHONPATH=assessment_overlay:platform/core/src:. .cache/operator-venv/bin/python -B assessment_overlay/operator_setup.py --run-dir "$ASSESSMENT_RUN_DIR" --execute
PYTHONPATH=assessment_overlay:platform/core/src:. .cache/operator-venv/bin/python -B assessment_overlay/operator_janitor.py --run-dir "$ASSESSMENT_RUN_DIR" --execute
PYTHONPATH=assessment_overlay:platform/core/src:. .cache/operator-venv/bin/python -B assessment_overlay/operator_cluster.py --run-dir "$ASSESSMENT_RUN_DIR" --gke-version "$ASSESSMENT_GKE_VERSION" --terraform .cache/platform-tools/terraform --execute
PYTHONPATH=assessment_overlay:platform/core/src:. .cache/operator-venv/bin/python -B assessment_overlay/operator_images.py --run-dir "$ASSESSMENT_RUN_DIR" --images-lock platform/clouds/gke/release-rc1.lock.json --execute
PYTHONPATH=assessment_overlay:platform/core/src:. .cache/operator-venv/bin/python -B assessment_overlay/operator_admission.py --run-dir "$ASSESSMENT_RUN_DIR" --execute
PYTHONPATH=assessment_overlay:platform/core/src:. .cache/operator-venv/bin/python -B assessment_overlay/operator_apply.py --run-dir "$ASSESSMENT_RUN_DIR" --kubectl .cache/platform-tools/kubectl --execute
PYTHONPATH=assessment_overlay:platform/core/src:. .cache/operator-venv/bin/python -B assessment_overlay/live_case_runner.py --run-dir "$ASSESSMENT_RUN_DIR" --execute
```

The runner executes the exact twelve-case order, reads both durable ledgers
around each case, checks the independent janitor before every case, and invokes
cleanup even after a case failure. On an earlier setup/apply failure, invoke
`operator_cleanup.py --run-dir "$ASSESSMENT_RUN_DIR" --execute` immediately;
the independent janitor remains the fallback. The 180-minute deadline and
20/60 durable ceilings are enforced in code. The $50 ceiling is a spending
limit for the operator, not a real-time GCP billing claim: billing data may
lag, so the operator must track it and abort/clean up if its conservative
upper-bound estimate reaches $50. A receipt alone cannot prove final spend.
