# Repository map

Every folder has one job. This page names it, so no folder carries its own README. Earlier phases (the k3s templates,
the local two-agent stack, the phase 3–5 contracts and the Google SDP evaluation runs) are no longer on `main`; they stay
verifiable at the tags `v1-live-evidence` and `v2-live-evidence`.

## Root

| Path | Job |
| --- | --- |
| `README.md` | What the repository is and how to run it. |
| `Makefile` | Every entry point, listed at the top of the file: `test`, `test-policies`, `onboard`, `onboard-check`, `provider`, `plan`, `apply`, `up`, `down`, `port-forward`, `agent-forward`, `fault`, `attack`, `corpus-live`, `inventory`, `demo-check`, `seed-demo`, `demo-reset`, `secrets`, `passphrase-check`, `passphrase`. |
| `LICENSE` | MIT. |
| `requirements-*.in` / `.txt` | Hash-locked dependency sets; each image and CI job installs only its own set. |
| `pyproject.toml` and the dot files | Tool configuration (Python version, linters, Gitleaks, Docker context). |

## The platform

| Path | Job |
| --- | --- |
| `platform/core/src/agent_platform/` | The platform: front door (`app.py`), console data API (`console.py`), onboarding (`onboarding.py`), provider profiles (`providers.py`), redaction client, audit, Kubernetes client, Secrets generator, and the Security & Operations Agent (`ops/`). `programs/` holds the redactor, gateway bootstrap and other programs mounted into the pinned images by ConfigMap. |
| `platform/core/kubernetes/` | Manifests: namespaces, default-deny NetworkPolicies, RBAC, the ops agent's admission policy (`policies/admission.yaml`), quotas and workloads. |
| `platform/core/database/` | Platform SQL: the LiteLLM schema and the Financial Agent's `finance.sql` (row-level security, roles, sign-in lookup). |
| `platform/core/images/` | The app and ops image (`Dockerfile`, allowlist build context). |
| `platform/core/ui/` | The console UI (Map, Agents, Onboard, Ops, Break it) with its own fonts; the Financial Agent UI shares its `style.css`, `core.js` and fonts. |
| `platform/core/tests/` | Platform tests: manifest invariants, ops agent, approvals, onboarding, the synthetic corpus, and policies against a real kube-apiserver (envtest). |
| `platform/agents/financial/` | **Financial Agent** (tenant #1): its own image, web app, read-only tools, grounding and sign-in. |
| `platform/agents/platform-guide/` | **Platform Guide** (tenant #2, Node.js): answers questions from a docs index built from `docs/` at image build time; one read-only `docs_search` tool, no data. |
| `platform/clouds/gke/` | Everything Google-specific (see below). The cloud-agnostic platform is in `platform/core`. |
| `providers/` | Model provider profiles. `make provider P=<name>` renders the gateway configuration and egress allowlist from one; only active, owner-approved profiles render (`gemini.yaml` active, `claude.yaml` an inactive proof). |
| `policy/` | The vulnerability exception register (below). |

### `platform/clouds/gke/`

| Path | Job |
| --- | --- |
| `terraform/module` | Reusable module: network (no NAT, Private Google Access), private cluster, node pool 0⇄1, workload identities, CI workload identity pool, KMS attestor and Binary Authorization, audit sink. |
| `terraform/root` | This project's instance (backend prefix `portfolio/agent-platform`; bucket given at init). |
| `kubernetes` | Overlay: workload-identity annotations, Retain storage class, FQDN egress, API-server egress, NetworkLogging; `generated/` is the rendered output. |
| `images.json` | Signed, pinned image digests (reused qualified gateway, database and redactor; app, ops, Financial Agent and Platform Guide from CI). |
| `render.py` | Overlay to one manifest; refuses unless every platform invariant holds. |
| `lifecycle.py` | `make plan`, `apply`, `up`, `down`, `fault`, `port-forward`, `agent-forward`, `inventory`, `secrets`, `seed-demo`, and `attest`. |
| `attack_suite.py`, `corpus_live.py`, `requalify.py` | Live attacks (to `docs/evidence/attack-suite.json`), the synthetic corpus through the real redactor, model requalification. |
| `demo_check.py`, `demo_reset.py`, `passphrase.py` | Read-only readiness check, demo reset, approval passphrase check and replacement. |
| `token_guard.py` | User-ADC credential guard for Terraform (no static token). |

Contract: the module takes `project_id`, `project_number`, `gke_version` and the image digests, and gives the overlay
`control_plane_cidr`, `gateway_service_account`, the redactor account, `attestor`, `ci_workload_identity_provider` and
`ci_service_account`. An `eks/` or `aks/` module would provide the same outputs; see `docs/porting-guide.md`.

### `policy/`

`policy/empty-exceptions.json` is the active default: it approves nothing. The evaluator
(`scripts/evaluate-container-vulnerability-policy.py`, used by the KEV release gate) consumes a complete Trivy JSON
report, an exact digest-pinned subject, the current CISA KEV feed and this exception register. `policy/reviewed-image-exceptions.json`
holds the reviewed, scoped filelock exception for the app and ops images, which expires on 6 November 2026. A new approval must be reviewed and
bound to the exact subject and finding; this folder by itself grants no promotion.

## Shared code the platform runs on

These folders are copied whole into the images and stay as they are until after teardown, when `runtime/` and
`contracts/` move into `shared/`.

| Path | Job |
| --- | --- |
| `runtime/agents/` | Agent composition and controls (`controls.py`: the bounded injection assessor the Financial Agent's tools use). |
| `runtime/phase3/` | Trusted runtime types, the Google SDP adapter and the deterministic email redaction layer in front of the redactor. |
| `runtime/phase4/` | Prompt-injection assessment and tool-governance contracts. |
| `contracts/` | JSON Schema and OpenAPI contracts copied into the images. |
| `demo/` | UI assets and synthetic fixtures copied into the app image. |
| `tests/` | Tests of `runtime/` and `contracts/` (`tests/agents`, `tests/phase3`–`phase5`), run by `scripts/check.sh` and the CI `agents` and `google-sdp-offline-evaluation` jobs. |

## Assessment, checks and evidence

| Path | Job |
| --- | --- |
| `assessment_overlay/` | Live security assessment tooling (never deployed) and its evidence in `assessment_overlay/evidence/` (never edited). |
| `scripts/` | CI checks (`check.sh`, `validate.py`, `check-references.py`, `lint-repository.sh`, the lock checks, the supply-chain qualification, the KEV and reviewed-exception gates), plus the helper scripts that `runtime/` and its tests still call; those move with `runtime/` after teardown. |
| `docs/` | The few current docs: architecture, onboarding contract and developer guide, debugging, how to view, porting, this map, the platform and security pages, ADRs in `docs/architecture/decisions/`, and the operations runbook. |
| `docs/evidence/` | Live evidence: requalification, onboarding, Financial Agent, attack-suite runs, UI and Trivy records (never edited). |
| `.github/workflows/` | `ci.yml` and `supply-chain.yml` (the required checks `checks`, `agents`, `gitleaks`, `google-sdp-offline-evaluation`, `qualification`) and `agent-platform-images.yml` (after CI on `main`: build, Trivy, SBOM, push by digest, KEV gate, cosign, KMS attestation). |

## Kept until after teardown

| Path | Why it is still here |
| --- | --- |
| `evaluation/` | Qualification records bound by SHA-256; byte-identical until after teardown. `evaluation/agent-composition/` is also copied into the app image. |
| `infra/gcp/` | Terraform units from earlier phases; deleted after teardown. |
| `docker/google-sdp-context/` | Build definition of the pinned redactor image. |
| `archive/qualification-history/` | Historical lock inputs that kept tests use to rebuild the retained qualification subjects. |

## Request flow

User chat (Financial Agent):

```text
browser ──► agent-financial (sign-in, own-rows tools, grounding)
              │  every question: text ──► redactor (platform/core/src/agent_platform/programs/redactor_server.py)
              │                              └─► Sensitive Data Protection over Private Service Connect (fail-closed)
              └─► gateway (LiteLLM, per-agent virtual key + budget) ──► Vertex AI over Private Service Connect
              └─► Postgres (read-only role, row-level security) for tool data
```

Infrastructure demo (app): browser ──► `apps/app` (`app.py`, `runtime/agents/web.py`) ──► redactor ──► gateway ──► Vertex.

Platform Guide: browser ──► agent-platform-guide (Node.js, `src/server.js`, turn in `src/agent.js`): every model call
is redacted first (redactor ──► gateway ──► Vertex AI, at most 2 calls); the model may ask for the read-only
`docs_search` tool, which runs in the process over the docs index bundled at build time. No data, no database path.

Operations flow: `ops-agent` (`ops/`) watches registered workloads read-only → diagnoses a finding → proposes a restart
→ the owner approves in the operations page with a passphrase → `app` signs the proposal → `ops-agent` executes a
rollout restart, which the `ops-agent-bounded-remediation` admission policy limits to that one change. Every step emits
an audit line.

## Where each control lives

| Control | Where |
| --- | --- |
| Private cluster, Dataplane V2, no NAT, Private Service Connect | `platform/clouds/gke/terraform/module/main.tf`, `private_endpoints.tf` |
| Default-deny NetworkPolicy and allow-lists | `platform/core/kubernetes/policies/network.yaml`; per agent, generated by `onboarding.py` |
| Network deny logging | `platform/clouds/gke/kubernetes/gke.yaml` |
| Pod Security, quotas | `platform/core/kubernetes/namespaces/`, `policies/quotas.yaml` |
| RBAC and bounded remediation | `policies/ops-agent-rbac.yaml`, `policies/admission.yaml` |
| Binary Authorization, KMS attestor | `terraform/module/admission.tf`; signing in `.github/workflows/agent-platform-images.yml` |
| Image scan, SBOM, KEV gate, cosign | `agent-platform-images.yml`, `scripts/kev-release-gate.py` |
| Secret scanning | `.github/workflows/ci.yml` (`gitleaks`) |
| Model keys, budgets | `programs/bootstrap.py`, `onboarding.py` |
| Redaction | `programs/redactor_server.py`, `redaction.py`, `runtime/phase3/` |
| Row-level security | `platform/core/database/finance.sql` |
| Audit | `audit.py` → Cloud Logging bucket (`terraform/module/audit.tf`) |
| Per-control status | `docs/platform/inventory.md`, `docs/agent-platform/claims-matrix.md` |

## Where to start

1. `README.md`, this map, and `docs/HOW-TO-VIEW.md` to open the pages.
2. `docs/agent-onboarding-contract.md`: what an onboarded agent inherits.
3. `platform/agents/financial/agent.yaml`, then the rest of `platform/agents/financial/`.
4. `platform/core/src/agent_platform/ops/`: the Security & Operations Agent.
5. `docs/evidence/`: what was tested live, and when.
