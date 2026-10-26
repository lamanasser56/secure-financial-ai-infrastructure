# Release handoff — 26 October 2026

**Never display the original GCP project ID or number**, including logs, filenames or screenshots. Keep credentials, raw requests, private kubeconfig and assessment state out of Git. No project, cluster, billing or janitor mutation occurred in this handoff turn.

## Repository state

- Main SHA: `9a9403579e4f8bfad48e1041344d8ccf2fdd54b1` (PR #170 rebase merge). Refresh before action: `git fetch origin main && git rev-parse origin/main`.
- Merged: PRs #146–#169 implemented the approved 20 themes and hosted/portable fixes; [#170](https://github.com/lamanasser56/secure-financial-ai-infrastructure/pull/170) merged with all five checks green.
- Open: [#171](https://github.com/lamanasser56/secure-financial-ai-infrastructure/pull/171), branch `docs/release-handoff`, contains only the repository copy of this handoff; #170 feature branch is closed. Current release lock is the older assessed release, **not** final S/R. No final freeze S, lock promotion R, new deployment or new live assessment has occurred.
- #170 contains the repository-owned disposable 12-case assessment with independent hosted janitor, exact-image provenance/admission, bounded durable ledgers and cleanup. Its 56 targeted offline tests passed on `sfai-engineering`. The live run has **not** occurred.
- Last merged PR: #170. Current theme: release handoff only. Branch state: main at the SHA above; open #171 carries only the repository copy of this note. Next step in this turn: check the automatic post-#170 hosted image run and stop. The next tool begins the S→R sequence below.

## Hosted image evidence

[Run 40321980381](https://github.com/lamanasser56/secure-financial-ai-infrastructure/actions/runs/40321980381) built all seven from `680150f307a59ab88b84c757d31dd4e2c85ddc70` after #167. Each passed full Trivy/KEV (zero unreviewed HIGH/CRITICAL, zero KEV), verified keyless signature and KMS attestation. No-fix counts below are post-push Trivy vulnerability entries without `FixedVersion`; these are **not** final S images.

| Image | Built | Gate | No-fix | Signed | Attested |
| --- | --- | --- | ---: | --- | --- |
| agent-platform-app | yes | pass | 23 | yes | yes |
| agent-platform-ops | yes | pass | 23 | yes | yes |
| agent-financial | yes | pass | 23 | yes | yes |
| platform-guide | yes | pass | 31 | yes | yes |
| agent-platform-gateway | yes | pass | 23 | yes | yes |
| agent-platform-redactor | yes | pass | 23 | yes | yes |
| agent-platform-database | yes | pass | 0 | yes | yes |

Later [run 40327178150](https://github.com/lamanasser56/secure-financial-ai-infrastructure/actions/runs/40327178150) for main `c485905e7159a2bf03785a1e36091169b6615f7d`: App, Ops and Financial built, passed gate, signed and attested (23 no-fix each). Guide **failed** at step `Push by digest, keyless sign, verify, KMS attest`; Redactor was cancelled by fail-fast; Gateway/Database were skipped as unchanged. The job log was unavailable through CLI, so the narrower failing command is unknown. After #170, inspect the automatic main-push image workflow per image. At most **two** fix/retry attempts; no gate/policy change.

## Read-only VM inventory

All three VMs are **RUNNING**; none was stopped or deleted.

| VM | Purpose / who created it | Needed |
| --- | --- | --- |
| `gke-agent-platform-work-6d502b75-pp3k` | Current deployment node; creation audit: GKE service agent. | Yes until owner-directed teardown. |
| `secure-infra-worker` | Prior evaluation/interactive worker; creation audit: owner's account. | No release dependency; retain until owner explicitly orders deletion. Worker-access Terraform/state was destroyed; never recreate. |
| `sfai-engineering` | Interactive code/tests; Codex created it using owner's identity (`managed-by=codex`). | Retain for interactive work until owner explicitly orders deletion; never release builds. |

## Non-negotiable rules and dates

1. `AGENTS.md`: portable, repository-declared build/release/deploy/test/assessment from fresh GitHub-hosted runners or another cloud. No personal laptop, `secure-infra-worker` or hand-installed state. Engineering VM is interactive only.
2. Unchanged vulnerability gate: unreviewed HIGH/CRITICAL or **any KEV** blocks. Add no exception. Exact App/Ops `filelock` exception in `policy/reviewed-image-exceptions.json` expires **2026-11-06**. Refresh every pinned base before S; fix every available-fix finding at any severity; enumerate no-fix findings by image. Stop on gate failure or an available fix that cannot be fixed.
3. **Build final images before 2026-11-06; GCP credits end 2026-11-07.** Do not budget a late retry.
4. 25 October assessment rules: disposable project, independent janitor **and** operator, zero external LLM calls, synthetic data, setup reserve 2 completed redactions/4 SDK attempts, D02 4/10, R01 2/5, planned 8/19, manual stop 12/40, hard 20/60, 180-minute deadline, $50 operator spending ceiling, complete resource absence, billing unlink and project deletion request. Original project and retained VMs are outside cleanup. Billing telemetry may lag; the $50 bound needs conservative operator monitoring, not a receipt-only claim.
5. Historical WSL scripts are read-only behavior/safety reference and never a runtime dependency. No historical PASS qualifies new images. No attack against the live cluster until the final authorized phase. The user reserved all further cloud release/deploy/assessment work for **another tool**; this document does not authorize this turn to execute it.

## Remaining ordered sequence — exact repository entry points

Run in a clean fresh cloud operator checkout. Private values are supplied by secure environment, never pasted into output. Stop at the first failed prerequisite.

### 1. Freeze S

```bash
git fetch origin main
git switch --detach origin/main
S=$(git rev-parse HEAD)
git status --porcelain
gh run list -R lamanasser56/secure-financial-ai-infrastructure -w ci.yml --commit "$S" --limit 5
```

Require clean status and successful **main-push CI for exactly S**. Any copied image input change afterward requires a new S and full build.

### 2. Force-build all seven from S on hosted runners

```bash
gh workflow run agent-platform-images.yml -R lamanasser56/secure-financial-ai-infrastructure --ref main
gh run list -R lamanasser56/secure-financial-ai-infrastructure -w agent-platform-images.yml --commit "$S" --limit 5
gh run view "$IMAGE_RUN_ID" -R lamanasser56/secure-financial-ai-infrastructure --json headSha,status,conclusion,jobs
gh run download "$IMAGE_RUN_ID" -R lamanasser56/secure-financial-ai-infrastructure -D "$PRIVATE_IMAGE_EVIDENCE_DIR"
```

The manual dispatch forces the matrix. Require seven successful image jobs and `headSha == S`. Inspect seven `*-evidence/receipt.json`, `trivy-full.json`, `predicate.json` artifacts privately. Record gate, no-fix findings, signed/attested for each. Stop on gate failure or any fixable finding left; max two fix attempts.

### 3. Verify exact subjects cryptographically

```bash
make tools operator-env
bash scripts/install-qualification-tools.sh "$PWD/.cache/platform-tools"
export PATH="$PWD/.cache/platform-tools:$PATH"
PYTHONPATH=platform/core/src:assessment_overlay:. .cache/operator-venv/bin/python -B scripts/image-provenance.py --verify-ref "$EXACT_DIGEST_REF" --project "$PRIVATE_PROJECT_ID" --source "$S" --predicate "$PRIVATE_IMAGE_EVIDENCE_DIR/$IMAGE_NAME-evidence/predicate.json" --cosign .cache/platform-tools/cosign
```

Repeat for seven exact digest refs, and require `Verifier.signature(ref)` and `Verifier.attestation(ref)` from `platform/core/src/agent_platform/release_verify.py` to return true for each. `assessment_overlay/operator_images.py::verify_source` shows the seven-image verifier loop. This checks Fulcio identity/workflow SHA, signed source/material predicate and KMS public-key signature. A tag or workflow receipt is insufficient.

### 4. Promote metadata-only lock R

```bash
git switch -c release/lock-r "$S"
${EDITOR:-vi} platform/clouds/gke/release-rc1.lock.json
git diff --name-only "$S"
git add platform/clouds/gke/release-rc1.lock.json docs/evidence
git commit -m "Promote exact S image subjects"
git push -u origin release/lock-r
gh pr create -R lamanasser56/secure-financial-ai-infrastructure --base main --head release/lock-r --title "Promote exact S image subjects" --body-file "$PRIVATE_PR_BODY_FILE"
```

Set `schema_version: 2`, `source_commit: S`, all seven logical image digests from S receipts, and `provenance` per image (`git_archive_sha256`, `input_fingerprint`, `materials`) from signed predicates. Preserve `runtime_contract` and `PROJECT_ID` registry placeholder; update stale `_comment`. `assessment_overlay/operator_images.py::source_subjects` defines exact shape. Diff from S may contain **only lock/evidence metadata**; if image inputs changed, restart S. Require green CI, merge R and record R SHA.

### 5. Deploy the same digests and check readiness

```bash
git fetch origin main
git switch --detach origin/main
make up
make demo-check
```

Run from fresh repository-declared cloud environment, never owner laptop/worker VM. `make up` is staged apply. Require runtime digests, signature/attestation, posture and readiness to match R. Do not alter original-project billing/janitor.

### 6. Disposable live assessment and full cleanup

Privately set `ASSESSMENT_PROJECT_ID`, `ASSESSMENT_SOURCE_REGISTRY`, `ASSESSMENT_BILLING_ACCOUNT`, `ASSESSMENT_GKE_VERSION`, `ASSESSMENT_RUN_DIR` outside checkout, and `GH_TOKEN`. Read `assessment_overlay/LIVE_PROCEDURE_FILES.md`. Its exact commands are:

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

Runner cleans up after cases. On any earlier failure immediately run `PYTHONPATH=assessment_overlay:platform/core/src:. .cache/operator-venv/bin/python -B assessment_overlay/operator_cleanup.py --run-dir "$ASSESSMENT_RUN_DIR" --execute`; independent janitor is fallback. Require 12 PASS cases, absent resources, billing unlinked and deletion request; monitor conservative cost upper bound and abort at $50.

### 7. Restore and record current demo state

```bash
make demo-reset
make onboard-check F=docs/examples/rejected-agent/agent.yaml
make attack
make demo-check
```

Rejected onboarding fixture intentionally exits nonzero and must show current reasons. `make attack` runs **only in this final phase** against intended deployed cluster; require bound current-release evidence and owned-fixture cleanup. FAIL/NOT_EXERCISED are not PASS.

### 8. Click through and capture deployed 1440×900 screens

```bash
make port-forward
make agent-forward A=financial
make agent-forward A=platform-guide
```

Use separate terminals. Click every console screen/tab/button/drawer: Map, Agents/passports, Onboard, Try, Break it, Ops; Financial and Guide in English **and Arabic**. Check the three Map cells, connector lines/animations, audit-request strip, rejection details and zero false Ops posture findings. Capture each deployed screen at **1440×900** with S/R/digest context and send screenshots. Browser-test screenshots are not deployed evidence. `docs/operations/demo-runbook.md` has the full walkthrough.

## Maintenance

After every merged PR update this one `outputs/RESUME.md` with last PR, exact main SHA, current theme/branch, image build state and next step. Repository copy: `docs/operations/RELEASE-HANDOFF.md`. Arabic status after every three merged PRs. Do not stop/delete VMs without owner instruction or recreate worker-access Terraform.
