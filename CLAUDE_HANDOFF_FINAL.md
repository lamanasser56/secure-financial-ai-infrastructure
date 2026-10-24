# Claude Code final handoff — Agent Runtime Platform RC1

Prepared 2026-10-24 03:56 UTC. **Stop state:** no new cloud execution was started in this follow-up. No new live verdict was earned. The earlier live assessment remains 5 PASS, 2 INCONCLUSIVE, 33 NOT_EXECUTED; F1–F4 are **not formally closed**. The user has directed that no further runs or cloud resources be started after this handoff.

## Branch and integration boundary

- Separate pushed branch: [`rc1-live-followup`](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/rc1-live-followup). The last content commit before this handoff is `131436dca6841fe93129ba3f56060fdd203b71c9`. **The branch tip containing this handoff is the latest commit**; resolve its immutable SHA with `git rev-parse rc1-live-followup` (or the GitHub branch link). A file cannot contain the SHA of the commit that hashes the file itself. Do not merge into `main` automatically.
- Comparison base: GitHub `main` at `216fa0d99473545eb0a28f6d8c5e5e92fd5d43a8`. The exact name/status inventory below is a direct tree comparison against that commit, including this handoff and the branch-local ledger/billing receipt: **367 paths (43 added, 77 modified, 247 deleted)**. It is not a patch from the older assessment base `14b0743c…`. Main advanced independently, so the **247 deletions are divergence from main, not requested removals**. Selectively port reviewed RC1 changes onto current main; do not merge this entire old-base branch without reconciliation.
- Claude's original checkout `/home/lama/secure-financial-ai-infrastructure` remained clean at `14b0743c4037291aa5fe1793dc55caf0fec3047b` during this follow-up. This branch lives in `/home/lama/security-assessments/2026-10-22-independent-live/rc1-live-followup-worktree`.

## Platform fixes versus assessment apparatus

**Platform source to review for merge:** `platform/core/src/agent_platform/programs/phone_guard.py` detects the recorded inline US phone miss and Saudi mobile formats (including spaces/dashes and Arabic-Indic digits) before Google SDP; `platform/core/src/agent_platform/programs/redactor_server.py` invokes it while preserving the existing SDP policy and fail-closed response; `platform/core/kubernetes/kustomization.yaml` mounts it as a versioned ConfigMap input. `platform/core/tests/test_finance_db.py` adds the D06 cleared-scope regression. The branch also carries the previously prepared RC1 F1–F4 boundary source in `platform/core/src/agent_platform/{gateway_boundary.py,data_capability.py,boundary_http.py,ops/executor.py,...}`, Financial frontdoor/broker/worker, SQL and Kubernetes policy changes, and earlier local corrections; review those as an integrated migration against **current main**. `requirements-financial-agent.txt` contains the reviewed, hash-locked `cryptography==50.0.2` needed by Financial frontdoor. The requirements locks also retain the reviewed `aiohttp==3.14.5` and `certifi==2026.10.19` fixes. Do not substitute historical image digests for rebuilt code.

**Assessment only; do not ship as platform runtime:** `assessment_overlay/sdp_guard.py`, `seed_sdp.py`, `redactor_server.py`, `patch_redactor_bundle.py`, `ops_server_assessment.py`, `patch_ops_stub.py`, container probes, candidate packaging/lock, local tests, next-live plan, receipts and this branch-local verdict copy. The overlay has separate fsynced 20-completed-redaction and 60-SDK-attempt PVC ledgers. The 21st completed redaction is refused before SDK dispatch; simulated pod restart preserves counts. The Ops explanation stub refuses real gateway/redactor keys. The exact external files and generated ConfigMap must be separately qualified; they are not protected by an unchanged historical image signature.

Local evidence: [follow-up report](assessment_overlay/followup-report.md), [candidate lock](assessment_overlay/candidate-inputs.lock.json), [focused tests](assessment_overlay/evidence/focused-overlay-tests.txt), [existing SDP policy tests](assessment_overlay/evidence/existing-sdp-policy-tests.txt), [trusted boundary tests](assessment_overlay/evidence/trusted-boundary-tests.txt), [real local PostgreSQL D06](assessment_overlay/evidence/d06-local.json), [container redactor](assessment_overlay/evidence/container-redactor-final.txt), [container Ops](assessment_overlay/evidence/container-ops-final.txt), [render/dependency validation](assessment_overlay/evidence/source-render-validation.json), and [source preservation](assessment_overlay/evidence/change-and-preservation.json). Local tests passed 5 focused, 9 policy and 22 boundary cases. The real local PostgreSQL 16.2 cleared-scope query returned zero rows; the live D06 case remains inconclusive. No fresh image build, SBOM, scan, provenance, signature, attestation or GKE test was performed for these changes.

## 40-case live ledger and formal findings

The branch-local [40-row CSV](assessment_overlay/live-case-verdicts-final.csv) carries the prior verdicts with LF line endings only; its evidence paths refer to the original `live-recovery-2026-10-24` report directory. The immutable previous [source ledger](/home/lama/security-assessments/2026-10-22-independent-live/live-recovery-2026-10-24/live-case-verdicts.csv) and five PASS evidence files were not altered. **PASS:** D01, D03, O01, O02, K06. **INCONCLUSIVE:** D02, D06. **NOT_EXECUTED:** all other 33. No PASS was rerun.

| Case | Verdict | Evidence |
| --- | --- | --- |
| A01 | NOT_EXECUTED | — |
| A02 | NOT_EXECUTED | — |
| A03 | NOT_EXECUTED | — |
| A04 | NOT_EXECUTED | — |
| A05 | NOT_EXECUTED | — |
| A06 | NOT_EXECUTED | — |
| A07 | NOT_EXECUTED | — |
| A08 | NOT_EXECUTED | — |
| D01 | PASS | evidence/f1-direct-gateway-live.json |
| D02 | INCONCLUSIVE | evidence/d02-real-sdp-synthetic-canaries.json; evidence/d02-policy-matching-phone-live.json |
| D03 | PASS | evidence/f1-redactor-egress-failure-live.json |
| D04 | NOT_EXECUTED | evidence/f2-worker-capability-live.json |
| D05 | NOT_EXECUTED | evidence/f2-f3-f4-real-boundaries.json |
| D06 | INCONCLUSIVE | evidence/f2-f3-f4-real-boundaries.json |
| D07 | NOT_EXECUTED | evidence/f2-f3-f4-real-boundaries.json |
| D08 | NOT_EXECUTED | — |
| O01 | PASS | evidence/f2-f3-f4-real-boundaries.json |
| O02 | PASS | evidence/f4-replay-process-epoch-live.json |
| O03 | NOT_EXECUTED | — |
| O04 | NOT_EXECUTED | — |
| K01 | NOT_EXECUTED | — |
| K02 | NOT_EXECUTED | evidence/f2-f3-f4-real-boundaries.json |
| K03 | NOT_EXECUTED | — |
| K04 | NOT_EXECUTED | — |
| K05 | NOT_EXECUTED | — |
| K06 | PASS | evidence/setup-admission-negative.json |
| R01 | NOT_EXECUTED | evidence/f2-f3-financial-real-http.json |
| R02 | NOT_EXECUTED | — |
| R03 | NOT_EXECUTED | — |
| R04 | NOT_EXECUTED | — |
| R05 | NOT_EXECUTED | — |
| R06 | NOT_EXECUTED | — |
| R07 | NOT_EXECUTED | — |
| R08 | NOT_EXECUTED | — |
| X01 | NOT_EXECUTED | — |
| X02 | NOT_EXECUTED | — |
| X03 | NOT_EXECUTED | — |
| X04 | NOT_EXECUTED | — |
| X05 | NOT_EXECUTED | — |
| X06 | NOT_EXECUTED | — |

- **F1 (mandatory gateway redaction): OPEN / not formally closed.** Prior live direct-gateway and redactor-failure negatives passed, but D02 end-to-end phone/JSON coverage was incomplete and the new pre-mask has not run on GKE.
- **F2 (trusted RLS identity): OPEN / not formally closed.** Prior PostgreSQL and capability negatives supported the boundary, but live D06 lacked the cleared-scope requery and D04/D05/D07 are incomplete.
- **F3 (Financial least privilege): OPEN / not formally closed.** Prior worker/database restrictions and legitimate Financial flow passed, but the complete original privilege and cross-user case set is incomplete.
- **F4 (independent Ops approval): OPEN / not formally closed.** Prior direct patch denial and approved/replay behavior passed, but O03 UID/resource-version race, O04 observe-only/deputy, and related K02 negatives are incomplete.

F5–F15 statuses are **unchanged from** [the prior register](/home/lama/security-assessments/2026-10-22-independent-live/rc1-release/vulnerability-register.csv); local follow-up checks did not close them: F5 PARTIALLY MITIGATED; F6 NOT VERIFIED; F7 NOT VERIFIED; F8 NOT VERIFIED; F9 OPEN; F10 PARTIALLY MITIGATED; F11 NOT VERIFIED; F12 NOT VERIFIED; F13 NOT VERIFIED; F14 NOT VERIFIED; F15 NOT VERIFIED. The assessment ledger is not evidence that these wider mechanisms passed.

## Cleanup, billing and cost

The **previous** live run's independent [resource absence receipt](/home/lama/security-assessments/2026-10-22-independent-live/live-recovery-2026-10-24/evidence/confirmed-final-independent-resource-cleanup-final.json), [final reconciliation](/home/lama/security-assessments/2026-10-22-independent-live/live-recovery-2026-10-24/evidence/final-closure-reconciliation.json), and [full execution report](/home/lama/security-assessments/2026-10-22-independent-live/live-recovery-2026-10-24/final-execution-report.md) verify cluster/nodes/disks/network/endpoint/registry/bucket/attestor cleanup, four temporary original-resource grant removals, baseline IAM/API restoration, and billing unlinking at that run's end. This handoff made **no cloud mutations or new paid resources**. A fresh read-only [billing receipt](assessment_overlay/evidence/final-billing-readback.json) at 2026-10-24 03:55 UTC confirms `billingEnabled=false` and no linked account. No new resource inventory was possible while the relevant APIs remained disabled; do not describe this as a fresh resource-absence read. Prior cumulative known-category/projection estimate was about **USD7.13**, not a settled invoice. No new charge was initiated here.

## Priority for Claude Code

1. Reconcile this branch against current `main` and port the actual platform fixes without importing the old-base deletions; retain all historical source locks, images, signatures and evidence. Review the phone guard and Financial dependency lock as explicit runtime inputs.
2. If future live work is authorized, requalify changed App/Ops image content and **all** changed external files with exact digests, SBOM, all-severity/KEV scans, build provenance, Cosign and Binary Authorization attestations. Reverify unchanged Financial/Guide bytes and trust if republished; check positive/negative admission, runtime imageIDs and mounted-file hashes. Preserve Fail/Deny and the proven ConfigMap-before-binding order.
3. Under a **new, explicit execution instruction** only, use the [twelve-case subset](assessment_overlay/next-live-subset.md): D02/D06, D04/D05/D07, O03/O04, K01/K02/K03/K05 and R01, plus its setup reserve. Planned maximum 8 completed redactions/19 SDK attempts, manual stop 12/40, hard ceilings 20/60; read both durable ledgers before/after each case. Zero external LLM and synthetic data only. The user excluded every other original case in the last authorized subset and has now instructed no new run.
4. Only after these real negative and legitimate flows pass, reassess F1–F4 closure. R03–R07 load/chaos/DR and other excluded cases need separate future authorization. Preserve any new evidence, maintain the cumulative USD20 ceiling, and independently verify cleanup/billing unlinking after any future authorized run.

## Exact paths changed against GitHub main `216fa0d99473545eb0a28f6d8c5e5e92fd5d43a8`

Status legend: `A` added, `M` modified, `D` present on main but absent from this old-base branch. This is a literal file inventory, **not** a recommendation to apply every difference.

```text
M	.github/workflows/agent-platform-images.yml
M	.github/workflows/ci.yml
D	.github/workflows/evaluate-presidio-2.2.364.yml
D	.github/workflows/release-google-sdp-evaluation.yml
A	CLAUDE_HANDOFF_FINAL.md
M	README.md
D	archive/qualification-history/README.md
A	assessment_overlay/candidate-inputs.lock.json
A	assessment_overlay/container_ops_probe.py
A	assessment_overlay/container_redactor_probe.py
A	assessment_overlay/evidence/change-and-preservation.json
A	assessment_overlay/evidence/container-ops-final.txt
A	assessment_overlay/evidence/container-redactor-final.txt
A	assessment_overlay/evidence/d06-local.json
A	assessment_overlay/evidence/existing-sdp-policy-tests.txt
A	assessment_overlay/evidence/final-billing-readback.json
A	assessment_overlay/evidence/focused-overlay-tests.txt
A	assessment_overlay/evidence/source-render-validation.json
A	assessment_overlay/evidence/trusted-boundary-tests.txt
A	assessment_overlay/followup-report.md
A	assessment_overlay/live-case-verdicts-final.csv
A	assessment_overlay/next-live-subset.md
A	assessment_overlay/ops_server_assessment.py
A	assessment_overlay/package_candidate.py
A	assessment_overlay/patch_ops_stub.py
A	assessment_overlay/patch_redactor_bundle.py
A	assessment_overlay/rc1-followup-source.tar.gz
A	assessment_overlay/redactor_server.py
A	assessment_overlay/run_local_d06.py
A	assessment_overlay/sdp_guard.py
A	assessment_overlay/seed_sdp.py
A	assessment_overlay/test_followup.py
D	database/README.md
D	database/reference/README.md
D	database/reference/migrations/001_tenant_schema.sql
D	database/reference/migrations/002_documents_rls.sql
D	database/reference/tests/001_tenant_schema_checks.sql
D	database/reference/tests/002_documents_rls_behavior.sql
D	database/reference/tests/002_documents_rls_checks.sql
D	database/security-contract.md
D	deploy/local-agents/litellm-schema.sql
D	deploy/local-agents/litellm-stub.yaml
D	deploy/local-agents/litellm-vertex.yaml
D	deploy/local-agents/tenant.sql
D	docker/google-sdp-evaluation/Dockerfile
D	docker/google-sdp-evaluation/README.md
D	docker/google-sdp-evaluation/candidates.json
D	docker/litellm-candidate/Dockerfile
D	docker/litellm-candidate/Dockerfile.dockerignore
D	docker/litellm-candidate/README.md
D	docker/presidio-bounded/Dockerfile
D	docker/presidio-bounded/Dockerfile.dockerignore
D	docker/presidio-bounded/README.md
D	docker/presidio-bounded/server.py
M	docs/HOW-TO-VIEW.md
M	docs/README.md
M	docs/REPO-MAP.md
M	docs/agent-developer-guide.md
M	docs/agent-onboarding-contract.md
D	docs/agent-platform/gate-1-bundle.md
D	docs/agents/README.md
D	docs/agents/adr-001-bounded-demo-agents.md
D	docs/agents/adr-002-ephemeral-conversations.md
D	docs/agents/architecture.md
D	docs/agents/identity-and-gateway-preparation.md
D	docs/agents/integrated-local-demo.md
D	docs/agents/integrated-synthetic-execution-checkpoint.md
D	docs/agents/live-follow-up-bundle.md
D	docs/agents/live-integration.md
D	docs/agents/live-isolated-application.md
D	docs/agents/live-preparation-status.md
D	docs/agents/offline-integration-contracts.md
D	docs/agents/operations-live-execution-bundle.md
D	docs/agents/recoverable-agent-application.md
D	docs/agents/recoverable-agent-execution-checkpoint.md
D	docs/agents/redactor-qualification.md
D	docs/agents/security-operations-local.md
M	docs/architecture.md
D	docs/architecture/README.md
D	docs/architecture/agent-runtime.md
D	docs/architecture/ai-gateway.md
M	docs/architecture/decisions/ADR-004-bounded-google-sdp-evaluation.md
M	docs/architecture/decisions/ADR-005-us-east1-synthetic-sdp-evaluation.md
M	docs/architecture/decisions/ADR-006-redaction-qualification-scope.md
M	docs/architecture/decisions/ADR-007-context-pattern-redaction-candidate.md
D	docs/architecture/dependency-map.md
D	docs/architecture/network-architecture.md
D	docs/architecture/system-architecture.md
D	docs/architecture/tenant-architecture.md
D	docs/architecture/tls-ingress-baseline.md
M	docs/console/design-spec.md
D	docs/observability.md
D	docs/operations.md
D	docs/operations/README.md
D	docs/operations/backup-restore.md
D	docs/operations/k3s-audit-logging.md
D	docs/phase3/README.md
D	docs/phase3/phase-3a-gateway-contract.md
D	docs/phase3/phase-3b-redaction-contract.md
D	docs/phase3/phase-3c-trusted-runtime-contract.md
D	docs/phase4/README.md
D	docs/phase4/phase-4-closure.md
D	docs/phase4/phase-4c-policy-injection-approval-audit-contract.md
D	docs/phase5/README.md
D	docs/phase5/security-boundaries.md
M	docs/platform/inventory.md
A	docs/releases/rc1-boundary-migration.md
A	docs/releases/rc1.md
M	docs/security/README.md
D	docs/security/google-sdp-agent-coverage.md
D	docs/security/google-sdp-agent-integration-retirement.md
D	docs/security/google-sdp-agent-preparation-checkpoint.md
D	docs/security/google-sdp-agent-qualification-plan.md
D	docs/security/google-sdp-context-campaign-execution-bundle.md
D	docs/security/google-sdp-context-diagnostic-execution-bundle.md
D	docs/security/google-sdp-context-diagnostics.md
D	docs/security/google-sdp-context-email-diagnostics.md
D	docs/security/google-sdp-context-execution-bundle.md
D	docs/security/google-sdp-context-policy.md
D	docs/security/google-sdp-email-diagnostic-execution-bundle.md
D	docs/security/google-sdp-evaluation-plan.md
D	docs/security/google-sdp-feasibility.md
D	docs/security/google-sdp-live-runbook.md
D	docs/security/google-sdp-milestone-readiness.md
D	docs/security/google-sdp-provenance-decision.md
D	docs/security/google-sdp-regional-eligibility.md
D	docs/security/google-sdp-synthetic-execution-proposal.md
D	docs/security/kms-ownership.md
D	docs/security/security-baseline.md
D	docs/supply-chain.md
D	docs/ui-redesign-proposal.md
D	evaluation/agent-composition/service-qualification.json
D	evaluation/google-sdp-agent/README.md
D	evaluation/google-sdp-agent/acceptance.json
D	evaluation/google-sdp-agent/obfuscated-email-candidate.json
D	evaluation/google-sdp-agent/offline-fixtures.json
D	evaluation/google-sdp-agent/offline-fixtures.schema.json
D	evaluation/google-sdp-agent/qualification.json
D	evaluation/google-sdp-context/README.md
D	evaluation/google-sdp-context/campaign-offline-result.json
D	evaluation/google-sdp-context/campaign-qualification.json
D	evaluation/google-sdp-context/diagnostic-offline-result.json
D	evaluation/google-sdp-context/diagnostic-qualification.json
D	evaluation/google-sdp-context/offline-result.json
D	evaluation/google-sdp-context/qualification.json
D	evaluation/google-sdp/corpus.json
D	evaluation/google-sdp/corpus.schema.json
D	evaluation/google-sdp/execution-profile.json
D	evaluation/google-sdp/result.schema.json
D	evaluation/litellm-candidate/qualification.json
D	evaluation/operations/restoration-qualification.json
D	evaluation/presidio-bounded/qualification.json
M	infra/gcp/agent-synthetic-demo/README.md
M	infra/gcp/google-sdp-evaluation-cluster/README.md
M	infra/gcp/google-sdp-evaluation/README.md
M	infra/gcp/operations-synthetic-demo/README.md
D	k3s/audit-policy.yaml
D	kubernetes/apps/google-sdp-evaluation/README.md
D	kubernetes/apps/google-sdp-evaluation/configmap.yaml
D	kubernetes/apps/google-sdp-evaluation/fqdnnetworkpolicy.yaml
D	kubernetes/apps/google-sdp-evaluation/job.yaml
D	kubernetes/apps/google-sdp-evaluation/kustomization.yaml
D	kubernetes/apps/google-sdp-evaluation/limitrange.yaml
D	kubernetes/apps/google-sdp-evaluation/namespace.yaml
D	kubernetes/apps/google-sdp-evaluation/native-gke/networklogging.yaml
D	kubernetes/apps/google-sdp-evaluation/networkpolicy.yaml
D	kubernetes/apps/google-sdp-evaluation/resourcequota.yaml
D	kubernetes/apps/google-sdp-evaluation/serviceaccount.yaml
D	kubernetes/apps/litellm/deployment.yaml
D	kubernetes/apps/litellm/kustomization.yaml
D	kubernetes/apps/litellm/network-policies.yaml
D	kubernetes/apps/litellm/service.yaml
D	kubernetes/apps/litellm/serviceaccount.yaml
D	kubernetes/apps/presidio/configmap.yaml
D	kubernetes/apps/presidio/deployments.yaml
D	kubernetes/apps/presidio/kustomization.yaml
D	kubernetes/apps/presidio/network-policies.yaml
D	kubernetes/apps/presidio/serviceaccounts.yaml
D	kubernetes/apps/presidio/services.yaml
D	kubernetes/base/kustomization.yaml
D	kubernetes/examples/README.md
D	kubernetes/examples/backup-cronjob.example.yaml
D	kubernetes/examples/migration-job.example.yaml
D	kubernetes/examples/rbac-configmap-reader.example.yaml
D	kubernetes/examples/storage-classes.example.yaml
D	kubernetes/namespaces/kustomization.yaml
D	kubernetes/namespaces/limit-range.yaml
D	kubernetes/namespaces/namespace.yaml
D	kubernetes/namespaces/resource-quota.yaml
D	kubernetes/network-policies/allow-dns-egress.yaml
D	kubernetes/network-policies/default-deny-egress.yaml
D	kubernetes/network-policies/default-deny-ingress.yaml
D	kubernetes/network-policies/kustomization.yaml
D	kubernetes/overlays/gke/README.md
D	kubernetes/overlays/gke/allow-nodelocal-dns.example.yaml
D	kubernetes/rbac/README.md
D	kubernetes/rbac/kustomization.yaml
D	kubernetes/rbac/serviceaccounts.yaml
D	kubernetes/secret-templates/README.md
D	kubernetes/secret-templates/litellm-master-key.secret.example.yaml
D	kubernetes/secret-templates/migration-database.secret.example.yaml
D	kubernetes/secret-templates/runtime-database.secret.example.yaml
M	platform/agents/financial/Dockerfile
M	platform/agents/financial/agent.yaml
M	platform/agents/financial/finance_agent/agent.py
M	platform/agents/financial/finance_agent/auth.py
A	platform/agents/financial/finance_agent/data_broker.py
A	platform/agents/financial/finance_agent/frontdoor.py
M	platform/agents/financial/finance_agent/ui/index.html
M	platform/agents/financial/finance_agent/ui/style.css
A	platform/agents/financial/finance_agent/worker.py
M	platform/agents/financial/tests/test_finance_agent.py
A	platform/agents/financial/tests/test_security_rc1.py
M	platform/agents/platform-guide/public/index.html
M	platform/agents/platform-guide/src/agent.js
M	platform/clouds/gke/kubernetes/gke.yaml
M	platform/clouds/gke/lifecycle.py
M	platform/clouds/gke/render.py
A	platform/core/database/finance-boundary.sql
M	platform/core/kubernetes/agents/financial.yaml
M	platform/core/kubernetes/agents/ops-observe.yaml
M	platform/core/kubernetes/agents/platform-access.yaml
M	platform/core/kubernetes/agents/platform-guide.yaml
M	platform/core/kubernetes/kustomization.yaml
M	platform/core/kubernetes/ops/workloads.yaml
A	platform/core/kubernetes/platform/boundaries.yaml
M	platform/core/kubernetes/platform/workloads.yaml
M	platform/core/kubernetes/policies/admission.yaml
M	platform/core/kubernetes/policies/network.yaml
M	platform/core/kubernetes/policies/ops-agent-rbac.yaml
M	platform/core/kubernetes/policies/quotas.yaml
A	platform/core/src/agent_platform/boundary_http.py
M	platform/core/src/agent_platform/console.py
A	platform/core/src/agent_platform/data_capability.py
A	platform/core/src/agent_platform/gateway_boundary.py
M	platform/core/src/agent_platform/onboarding.py
M	platform/core/src/agent_platform/ops/actions.py
M	platform/core/src/agent_platform/ops/agent.py
M	platform/core/src/agent_platform/ops/approval.py
A	platform/core/src/agent_platform/ops/executor.py
M	platform/core/src/agent_platform/ops/server.py
M	platform/core/src/agent_platform/platform_secrets.py
M	platform/core/src/agent_platform/programs/bootstrap.py
M	platform/core/src/agent_platform/programs/gateway_entry.py
A	platform/core/src/agent_platform/programs/phone_guard.py
M	platform/core/src/agent_platform/programs/redactor_server.py
A	platform/core/tests/test_auth_headers_rc1.py
A	platform/core/tests/test_branding_rc1.py
M	platform/core/tests/test_console.py
M	platform/core/tests/test_envtest_policies.py
M	platform/core/tests/test_finance_db.py
M	platform/core/tests/test_onboarding.py
A	platform/core/tests/test_ops_verification_rc1.py
M	platform/core/tests/test_platform.py
M	platform/core/tests/test_retire_agent.py
A	platform/core/tests/test_trusted_boundaries.py
M	platform/core/ui/agents.js
M	platform/core/ui/app.js
M	platform/core/ui/index.html
M	platform/core/ui/map.js
M	platform/core/ui/style.css
M	requirements-agent-composition.txt
D	requirements-agent-identity.in
D	requirements-agent-identity.txt
M	requirements-financial-agent.txt
M	requirements-google-sdp-runtime.txt
M	requirements-google-sdp.txt
M	requirements-litellm-candidate.txt
D	requirements-presidio-runtime.in
D	requirements-presidio-runtime.txt
D	runtime/agents/control_channel.py
D	runtime/agents/database_preparation.py
D	runtime/agents/isolated_application.py
D	runtime/agents/isolation_controller.py
D	runtime/agents/isolation_runtime.py
D	runtime/agents/service_restoration.py
D	runtime/agents/synthetic_scope_candidate.py
D	runtime/agents/trial_composition.py
D	runtime/phase3/sdp_qualification.py
D	scripts/bootstrap-operations-reasoning.py
D	scripts/bootstrap-synthetic-demo.py
D	scripts/build-google-sdp-evaluation-image.sh
D	scripts/build-litellm-candidate.sh
M	scripts/check-agent-preparation-locks.sh
D	scripts/check-local-agent-stack.py
D	scripts/check-presidio-runtime-lock.sh
M	scripts/check.sh
D	scripts/diagnose-sdp-email-context.py
D	scripts/evaluate-composite-email-campaign.py
D	scripts/evaluate-google-sdp.py
D	scripts/google-sdp-docker-config.py
D	scripts/google-sdp-image-config-id.py
D	scripts/inspect-sdp-qualification-preparation.py
D	scripts/local-agent-database-guard.py
D	scripts/local-agent-stack.py
D	scripts/local-agent-upstream.py
D	scripts/probe-google-sdp-egress.py
D	scripts/probe-synthetic-demo-application-egress.py
D	scripts/qualify-bounded-presidio.py
D	scripts/qualify-current-live-application.py
D	scripts/qualify-sdp-context-diagnostic-release.sh
D	scripts/qualify-sdp-context-release.sh
D	scripts/rehearse-integrated-demo.py
D	scripts/render-google-sdp-evaluation-job.sh
D	scripts/render-operations-reasoning-bundle.py
D	scripts/render-sdp-composite-email-campaign-job.sh
D	scripts/render-sdp-context-diagnostic-job.sh
D	scripts/render-sdp-context-job.sh
D	scripts/render-sdp-email-diagnostic-job.sh
D	scripts/render-synthetic-demo-bundle.py
D	scripts/render-worker-live-services.py
D	scripts/run-integrated-agents.py
D	scripts/run-qualified-local-agents.py
D	scripts/run-recoverable-agents.py
D	scripts/run-synthetic-live-catalog.py
D	scripts/serve-synthetic-demo-redactor.py
D	scripts/sign-native-demo-subject.py
D	scripts/stage-synthetic-demo-admission.py
D	scripts/supervise-synthetic-demo-gateway.py
D	scripts/test-reference-rls.sh
D	scripts/validate-composite-email-campaign-result.py
D	scripts/validate-google-sdp-deployment.sh
D	scripts/validate-google-sdp-execution.py
D	scripts/validate-google-sdp-gcp-bootstrap.sh
D	scripts/validate-sdp-composite-email-campaign-deployment.py
D	scripts/validate-sdp-context-campaign-result.py
D	scripts/validate-sdp-context-diagnostic-deployment.py
D	scripts/validate-sdp-context-job.py
D	scripts/validate-sdp-email-diagnostic-deployment.py
M	scripts/validate.py
D	scripts/verify-google-sdp-egress-evidence.py
D	scripts/verify-operations-image-qualification.py
M	tests/agents/test_actual_composition.py
D	tests/agents/test_admission_staging_mode.py
D	tests/agents/test_client_bootstrap_accounting.py
D	tests/agents/test_composite_email_wiring.py
D	tests/agents/test_control_channel.py
D	tests/agents/test_gateway_prisma_startup.py
D	tests/agents/test_independent_preparation_artifacts.py
M	tests/agents/test_integration_preparation.py
M	tests/agents/test_live_preparation.py
D	tests/agents/test_local_launcher.py
D	tests/agents/test_operations_bundle.py
D	tests/agents/test_service_restoration.py
D	tests/agents/test_synthetic_demo_admission.py
D	tests/agents/test_synthetic_scope_candidate.py
D	tests/agents/test_trial_composition.py
D	tests/agents/test_worker_live_services.py
D	tests/phase3/evaluation/test_google_sdp_evaluation.py
D	tests/phase3/evaluation/test_google_sdp_qualification.py
D	tests/phase3/evaluation/test_obfuscated_email_candidate.py
M	tests/phase3/evaluation/test_sdp_context_campaign.py
D	tests/phase3/runtime/test_composite_email_campaign.py
M	tests/phase3/runtime/test_deterministic_email.py
D	tests/phase3/runtime/test_sdp_email_context_diagnosis.py
D	tests/phase5/test_google_sdp_deployment_contract.py
D	tests/phase5/test_google_sdp_docker_config.py
D	tests/phase5/test_google_sdp_evaluation_image.py
D	tests/phase5/test_google_sdp_gcp_bootstrap.py
D	tests/phase5/test_google_sdp_image_config.py
D	tests/phase5/test_google_sdp_native_execution.py
D	tests/phase5/test_reference_rls.py
D	tests/phase5/test_sdp_context_campaign_release.py
D	tests/phase5/test_sdp_context_deployment.py
D	tests/phase5/test_sdp_context_diagnostic_deployment.py
D	tests/phase5/test_sdp_context_diagnostic_release.py
D	tests/phase5/test_sdp_email_diagnostic_deployment.py
```
