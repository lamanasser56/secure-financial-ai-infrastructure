# Security review, 13 October 2026

This review covers the Secure AI Agent Platform at commit `aa8fac7`. It is published now that every finding is either
fixed or documented as an accepted limitation. Each finding below gives its status and the evidence for it.

## Scope and method

- **Code and configuration:** `platform/core/kubernetes` (policies, RBAC, admission, NetworkPolicies), the GKE
  Terraform module, the gateway, redactor and agent programs, GitHub Actions and the dependency locks.
- **Tools:** Trivy 0.72.0 and Kubescape v3.0.45, pinned and hash-verified. Both scanned the rendered manifests (92
  objects) and the Terraform.
- **Cloud checks:** read-only (describe, list, get-iam-policy).
- **False-positive check:** every finding was checked by hand, including the findings of a separate independent audit.
- **Not covered:** live behaviour. The platform was down during the review; live behaviour is covered by the attack
  suite (`docs/evidence/attack-suite*.json`).

## Verified controls (no finding)

- **Cluster:** private nodes; the IP control-plane endpoint is disabled (DNS endpoint with IAM only). Shielded nodes
  with Secure Boot, Workload Identity, Dataplane V2 with FQDN policies.
- **Binary Authorization:** `ENFORCED_BLOCK_AND_AUDIT_LOG`, requiring the CI attestation.
- **Workloads:**
  - Pod Security `restricted` in every namespace;
  - default-deny NetworkPolicies;
  - quotas of 0 load balancers and 0 node ports;
  - no automounted tokens, except the ops agent's projected, audience-bound token.
- **Ops agent admission:** the ops agent can only restart or scale within bounds.
- **GitHub Actions:**
  - every action is pinned by full SHA;
  - no event data is interpolated into `run:`;
  - the default token is read-only;
  - every `pip install` uses `--require-hashes`;
  - base images are pinned by digest.
- **Kubescape:** NSA + MITRE compliance 96%. The flagged items were by-design or false positives: price fields
  matched as "secrets", the project registry flagged as untrusted, and the ops agent's bounded workload rights.

## Findings and status

| # | Severity | Finding | Status |
| --- | --- | --- | --- |
| 1 | HIGH | Unprotected `main` fed the image signing and attestation pipeline. | **Fixed.** Ruleset `protect-main`: PR required, 5 required checks (gitleaks included), no force push, no deletion, no bypass. Signing runs only after CI passes on a push to `main`, and only for that exact commit. PR #51, `docs/security/main-branch-protection.md`, `docs/evidence/governance-and-worker-2026-10-13.json`. |
| 2 | MEDIUM | Ops approval was checked against cached evidence, and the patch had no object precondition. | **Fixed.** Execution re-diagnoses from a fresh GET (same UID, digest and resourceVersion). The approval is bound to UID and resourceVersion, and the patch carries the resourceVersion as a precondition (409 on a race). PR #53, envtest, attack case `ops_stale_approval_refused`. |
| 3 | MEDIUM | Figures from the question passed numeric grounding. | **Fixed.** Figures must come from tool results or structured tool arguments, never from the question alone. PR #52, attack case `financial_question_figure_not_evidence` (EN/AR). |
| 4 | MEDIUM | The login throttle counted per client, so one user could lock out everyone behind port-forward. | **Fixed.** 5 failures lock that username only, plus a per-address backstop of 20. `X-Forwarded-For` is ignored. PR #52, attack case `financial_login_lockout_per_username`. |
| 5 | MEDIUM | CISA KEV was not an enforced release gate for every severity. | **Fixed.** Before signing, a full-severity scan of the pushed digest and a fresh, complete KEV feed. Any KEV finding blocks, then the HIGH/CRITICAL policy runs. PR #51; first live run passed on all three images. |
| 6 | MEDIUM | Data Access audit logs are not enabled. | **Accepted limitation** (`known-limitations.md`). |
| 7 | MEDIUM | Worker VM reachable over SSH from the Internet. | **Mitigated.** The VM is stopped (disk kept) and deleted at teardown. Nothing in the platform depends on it. |
| 8 | MEDIUM | The ops agent's proposals were never pruned. | **Fixed.** 300 s lifetime, older proposals superseded, history capped at 100. PR #53. |
| 9 | LOW | Per-user token and DLP ceilings are kept in memory. | **Partly fixed.** Missing or invalid usage is now charged as the per-call maximum (PR #52). The rest is an accepted limitation. |
| 10 | LOW | Mutations do not wait for a durable audit write. | **Accepted limitation.** |
| 11 | LOW | No alert policies, scheduled backups or restore drill. | **Accepted limitation.** |
| 12 | LOW | Session revocation and the throttle reset on restart. | **Fixed for sessions** (the epoch rotates at startup; attack case `financial_session_epoch_restart`). The throttle reset is an accepted limitation. |
| 13 | LOW | Audit log bucket retention is not locked. | **Accepted limitation.** Not locked on purpose: a lock cannot be undone and would block teardown. |
| 14 | LOW | Digits inside the user's own merchant or note fields blocked valid answers. | **Fixed.** Exempt only inside a verbatim quote of the whole stored string. PR #52, attack case `financial_merchant_with_digits_answers`. |
| 15 | LOW | No application-layer (CMEK) encryption for Kubernetes Secrets. | **Accepted limitation.** Google's default encryption at rest applies. |
| 16 | LOW | The repository does not require SHA pinning of Actions. | **Accepted limitation.** Every action is pinned today. |
| 17 | LOW | Worker host hardening items carried from the independent audit. | **Mitigated** by stopping the VM. It is deleted at teardown. |
| 18 | INFO | The redactor ignores SIGTERM. | **Accepted limitation** (availability only). |

**Note on finding #9, added 22 October 2026** (the row above is unchanged). An independent hostile-agent review
(Codex) on 22 October 2026 found that:

- the per-user ceilings are enforced in the agent's own code;
- a truncated model reply raises before the per-user token charge
  (`platform/agents/financial/finance_agent/agent.py:255`), so its tokens are not counted against the user;
- the DLP client budget is process-wide: one budget for all users of the agent, not one per user.

For a hostile agent the finding is re-graded **MEDIUM**. See the
[trust model](known-limitations.md#trust-model-the-agents-code-is-trusted).

## Evidence

- Final attack-suite run: `docs/evidence/attack-suite.json` (run 3, 18/19). The one failure is a documented test
  defect; the control held (`attack-suite-run-3-note.json`).
- Accepted limitations: `docs/security/known-limitations.md`.
- Added 22 October 2026: the latest attack-suite run is run 6, 2026-10-19, 19/19 (`docs/evidence/attack-suite.json`).
