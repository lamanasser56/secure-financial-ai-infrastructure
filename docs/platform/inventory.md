# Platform inventory (Phase 0, read-only)

> **Snapshot of 15 Oct 2026.** Kept as the Phase 0 record and not kept up to date; only the request ID and the approval-refusal lines below were corrected later. For the current status see the [claims matrix](../agent-platform/claims-matrix.md), the [claims inventory](../security/claims-inventory.md) and the [request trace](request-trace.md).

Taken from `main` on 2026-10-15 by reading the repository. Nothing here was re-tested; "live-tested" repeats what
`docs/agent-platform/claims-matrix.md` and `docs/evidence/` already record. The project ID is not shown anywhere.

Classes: **L** implemented + live-tested · **I** implemented, not live-tested · **D** documented only · **F** future.

## 1a. Security and infrastructure controls

| Control | Class | Proof (file) | Note |
| --- | --- | --- | --- |
| GKE private nodes, private endpoint, Dataplane V2 (`ADVANCED_DATAPATH`), FQDN policy, Shielded nodes, Workload Identity | L | `platform/clouds/gke/terraform/module/main.tf` | Evidence: `docs/evidence/` (2026-10-11 runs). |
| NetworkPolicy default-deny per namespace + allow-lists | L | `platform/core/kubernetes/policies/network.yaml`; generated per agent by `platform/core/src/agent_platform/onboarding.py` | Policies are also tested on a real kube-apiserver: `platform/core/tests/test_envtest_policies.py`. |
| NetworkPolicy deny logging | I | `platform/clouds/gke/kubernetes/gke.yaml` (`NetworkLogging`, `deny: {log: true}`) | Applied by `make up`; the claims matrix does not list a live log read-back. |
| Private Service Connect regional endpoints, no Cloud NAT, no external IPs | L | `terraform/module/private_endpoints.tf`, `main.tf` (`enable_private_nodes`, `private_ip_google_access`) | Claims matrix: live-tested 2026-10-11. |
| Binary Authorization + KMS attestor | L | `terraform/module/admission.tf`; policy `REQUIRE_ATTESTATION`; cluster `PROJECT_SINGLETON_POLICY_ENFORCE` in `main.tf` | `make attack` includes an unsigned-image attempt (`platform/clouds/gke/attack_suite.py`). |
| Cosign keyless signing, verify, SBOM, Trivy HIGH/CRITICAL gate | I | `.github/workflows/agent-platform-images.yml` | Runs only after CI passes on `main`. |
| Rekor transparency log | D | no explicit flag in the workflow | Keyless `cosign sign` uses Rekor by default; the repo never states or checks it. `scripts/qualify-signatures.sh` disables tlog only for offline test keys. |
| KEV release gate | I | `scripts/kev-release-gate.py`, step in `agent-platform-images.yml`; test `tests/phase5/test_kev_release_gate.py` | |
| gitleaks (full history, pinned, checksum-verified) | I | `.github/workflows/ci.yml` job `gitleaks` | Required check per `docs/security/main-branch-protection.md`. |
| Other CI checks | I | `ci.yml` jobs `checks`, `agents` (envtest, core tests, Financial Agent tests with real Postgres), `google-sdp-offline-evaluation`; `supply-chain.yml` job `qualification` | |
| LiteLLM virtual keys, budgets, rpm limits | L | `platform/core/src/agent_platform/programs/bootstrap.py` (`/key/generate`: `max_budget`, `budget_duration 30d`, `rpm_limit 20`); total capped at $10 in `onboarding.py` | |
| DLP redactor (Sensitive Data Protection + deterministic email layer), fail-closed | L | `platform/core/src/agent_platform/programs/redactor_server.py`, `redaction.py` (client), `runtime/phase3/` | Person names are not redacted (`claims-matrix.md`, limitations). Idle channel (Phase 0 item 4): gRPC keepalive every 60 s plus an idle-rebuild backstop; tested offline against a silently dropping path, not yet observed live. |
| Postgres FORCE ROW LEVEL SECURITY, non-owner NOBYPASSRLS roles | L | `platform/core/database/finance.sql`; `platform/core/tests/test_finance_db.py` | Live 2026-10-13. |
| Pod Security "restricted" | L | namespace labels in `platform/core/kubernetes/namespaces/namespaces.yaml` and generated `agents/*.yaml` | |
| RBAC (ops agent read-only roles; restart-only via admission policy) | L / I | `platform/core/kubernetes/policies/ops-agent-rbac.yaml`; `policies/admission.yaml` (ValidatingAdmissionPolicy) | Claims matrix marks the "cannot change what runs" claim as designed, attack suite pending. |
| Audit log | I | `platform/core/src/agent_platform/audit.py` (JSON lines on stdout) → Cloud Logging sink → 30-day bucket, `terraform/module/audit.tf` | Schema in 1d. Data Access logs are not enabled (known limitation). |
| Prometheus / Grafana / Alertmanager | **absent** | `main.tf` enables GKE Managed Prometheus collection only | No scrape config, dashboard, rule or alert route in the repo (`docs/observability.md` says so). Grafana and Alertmanager do not exist here. |
| Terraform with Application Default Credentials | I | `platform/clouds/gke/terraform/root`, `module/` | `make plan` / `make apply`; `terraform validate` and `fmt -check` run inside `make test`. |

## 1b. Current frontend

| Route | Served by | Files |
| --- | --- | --- |
| `/`, `/app.js`, `/style.css`, `/operations.html`, `/operations.js`, `/api/bootstrap`, `/api/conversation`, `/api/reset`, `/api/operations` | `runtime/agents/web.py` (`DemoServer`) inside the **app** deployment (`apps/app`, port 8080), started by `platform/core/src/agent_platform/app.py` | `platform/core/ui/{index,operations}.html`, `{app,operations}.js`, `style.css`. The image copies them over `/app/demo/ui/` (`platform/core/images/Dockerfile`). |
| `/`, `/app.js`, `/style.css`, `/healthz`, `/api/me`, `/api/expenses`, `/api/login`, `/api/logout`, `/api/ask` | `platform/agents/financial/finance_agent/server.py` in the **agent-financial** namespace, port 8081 | `platform/agents/financial/finance_agent/ui/{index.html,app.js,style.css}` |
| Not served | — | `demo/ui/*` is the older copy, kept byte-identical for qualification records; it is overwritten in the image. |

Ops agent API (cluster internal, bearer key): `/v1/health`, `/v1/snapshot`, `/v1/posture`, `/v1/execute` (`ops/server.py`).
Access is by `make port-forward` (8080) and `make agent-forward A=financial` (8081); there is no public ingress.

## 1c. Hello agent files

- `platform/agents/hello/agent.yaml`
- `platform/core/kubernetes/agents/hello.yaml` (generated)
- `platform/core/src/agent_platform/programs/hello_agent.py`
- `docs/evidence/onboarding-hello-live-2026-10-12.json`
- Referenced from: `Makefile` (`hello`, `NAME`), `platform/clouds/gke/lifecycle.py` (`hello`), generated `agents/kustomization.yaml`, `agents/platform-access.yaml`, `agents/ops-observe.yaml`, `platform/core/ui/{index.html,app.js,operations.js}`, `platform/core/tests/{test_onboarding,test_platform,test_ops_agent,test_envtest_policies}.py`, `platform/clouds/gke/attack_suite.py`, `docs/{REPO-MAP,agent-developer-guide,agent-onboarding-contract}.md`, `docs/agent-platform/claims-matrix.md`, `docs/evidence/attack-suite*.json`, `docs/evidence/financial-agent-live-2026-10-13.json`.

## 1d. Audit record schema (what exists today)

One JSON line per event: `audit_event`, `component`, `at` (epoch seconds) plus bounded fields. Content fields
(`text`, `prompt`, `content`, `token`, `key`, `secret`, `password`, `authorization`) are rejected by `audit.emit`.
One request ID is shared between events: see [request-trace.md](request-trace.md) (corrected after this snapshot).

| Event (component) | Fields |
| --- | --- |
| `redaction` (redactor) | `caller`, `categories` |
| `redaction_failed` / `redaction_rejected` (redactor) | `caller`, `reason` (exception type) |
| `finance_login` / `finance_login_failed` / `finance_login_throttled` / `finance_expense_added` (agent-financial) | `user_ref` (hash) where known |
| `finance_turn` (agent-financial) | `user_ref`, `outcome`, `reason`, `model_calls`, `tools` (ids), `tokens`, `masked` (categories) |
| `agent_tool` / `agent_turn` (app) | `event_id`, `event_type`, `agent`, `tenant_ref`, `outcome`, `model_attempts`, `tool_attempts`, `tool_id`, `authorization_result`, `injection_result`, `policy_outcome`, `policy_reason_code`, `governance_result` |
| `model_response_shape` (app) | `shape` |
| `ops_observed`, `ops_diagnosed`, `ops_proposed`, `ops_denied`, … (ops-agent) | `target`, `finding`, `evidence_digest`, `action`, `request_id`, desired/available counts |
| `ops_approval_signed` (app) | `request_id`, `target`, `action` |
| `ops_approval_refused` (app) | `request_id`, `stage` (`approve` or `execute`), `reason`, and `proposal_pending` on an approve refusal |
| `ops_approved`, `ops_executed`, `ops_denied` (ops-agent) | `target`, `request_id`, `approver` or `code` |
| `app_started`, `app_session_refreshed`, `app_session_refresh_failed`, `ops_agent_started`, `ops_scan_error` | session and lifecycle fields |

Missing for a per-request "what the platform did" trace:

| Wanted | Today |
| --- | --- |
| One request/correlation ID across app → redactor → gateway → tools | Present since this snapshot: `X-Request-ID`, logged as `request_id` by the app or agent, the redactor and the gateway hook ([request-trace.md](request-trace.md)). `finance_turn` carries it. |
| Caller identity | Only a hashed `user_ref` (Financial Agent) or `tenant_ref`; no agent-level identity in redactor lines beyond `caller`. |
| Redaction findings per request | Categories per redactor call; no counts, no link to the request. |
| Tool calls | Tool ids in `finance_turn.tools`; no per-call outcome or arguments (by design). |
| RLS outcome | Not recorded; RLS is enforced in Postgres and never reported. |
| Grounding check result | Not in the audit event. |
| Model, token cost | `tokens` per turn only; no model name, no cost. The LiteLLM spend log is a separate store. |
| Approval events | Proposed, approved, executed and denied (`ops_approved`, `ops_executed`, `ops_denied` with a code) are recorded by the ops agent; signed/refused by the app. The refusal records `stage` and `reason`; an approver identity beyond the fixed `owner` is not modelled. |

## 1e. Agent manifest `platform/agents/<name>/agent.yaml`

Closed shape, validated by `agent_platform.onboarding.validate`. Anything else is rejected with a reason.

| Key | Required | Rule |
| --- | --- | --- |
| `agent` | yes | equals the directory name; 3–22 chars `[a-z0-9-]`; not a reserved name |
| `team` | yes | 1–60 chars |
| `description` | yes | 1–200 chars |
| `placement` | yes | `namespace` |
| `runtime.image` | yes | an agent image present in `platform/clouds/gke/images.json`, not a platform image |
| `runtime.command` | yes | 1–8 short strings |
| `runtime.port` | yes | integer 1024–65535 |
| `runtime.replicas` | yes | 1 or 2 |
| `runtime.resources` | yes | `cpu` ≤ 250m, `memory` ≤ 256Mi |
| `model.budget_usd_month` | yes | float > 0 and ≤ 5.00; platform total ≤ $10 |
| `redaction` | yes | `required` |
| `tools` | yes | ≤ 5 of `{id, access: read, description}`; write-like names rejected |
| `data` | yes | `none`, or `{database: finance, agent_access: read, user_entry: none|own-rows, row_level_security: required}` |
| `operations` | no | `observe` only |

`make onboard A=<name>` writes, under `platform/core/kubernetes/agents/` (generated, "do not edit"): for each agent a
file `<agent>.yaml` with Namespace `agent-<name>` (Pod Security restricted), ResourceQuota, LimitRange, ServiceAccount
(no token), Deployment (hardened, secret mounted read-only), Service, NetworkPolicies (default-deny, DNS, egress to
redactor and gateway, Postgres only if declared); plus `platform-access.yaml` (ingress allow rules in `platform`),
`ops-observe.yaml` (read-only roles for the ops agent) and `kustomization.yaml`. It prints a summary of what the agent
inherits. `make test` runs `onboarding check`, which fails on drift. Gateway and redactor keys are created later by
`make up` (`platform_secrets`), not by `make onboard`.

## Teardown checklist (delete by 2026-11-06; credit expiry 2026-11-08)

Source of truth for the order is `docs/agent-platform/teardown-plan.md`. Resource types to be gone at the end:

- [ ] GKE cluster and node pool (`deletion_protection = false` first)
- [ ] VPC network, subnet, firewall rules created by the module
- [ ] Private Service Connect regional endpoints (Vertex, Sensitive Data Protection), their private DNS zones and A records
- [ ] **Postgres snapshots** named `agent-platform-postgres-<UTC stamp>` (one per `make down`; `lifecycle.py`)
- [ ] **Retained Postgres persistent disk** (StorageClass `agent-platform-retain`, reclaim `Retain`)
- [ ] **Audit log bucket** `agent-platform-audit` and its sink (export first if the records are needed; retention is 30 days)
- [ ] Default log bucket copies of workload logs (30-day retention; no action beyond bucket deletion)
- [ ] Binary Authorization policy reset, attestor, Container Analysis note
- [ ] Cloud KMS key versions scheduled for destruction (the key ring itself cannot be deleted)
- [ ] Artifact Registry repositories and images
- [ ] Workload Identity pool and provider (CI), service accounts (node, gateway, redactor, CI), custom role `predict`
- [ ] Standalone VM `secure-infra-worker` and its disk
- [ ] Terraform state bucket (last, after exporting sanitized summaries)
- [ ] Verification: `make inventory` all empty, then save `docs/evidence/final-inventory.json`; billing run-rate screenshot by the owner
