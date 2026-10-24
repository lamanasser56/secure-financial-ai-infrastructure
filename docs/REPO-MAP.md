# Repository map

This page sorts the repository into the current product (the Agent Runtime Platform), the shared code that product
runs on, and the history behind it. Start with **Product**. The **History** paths are kept as evidence and are not
part of the historical platform runtime. The proposed RC source is not deployed; see [the trusted-boundary migration](releases/rc1-boundary-migration.md).

The qualification records under `evaluation/` bind files by SHA-256: every file in `runtime/`, `contracts/` and
`demo/`, 14 files in `evaluation/`, 11 in `docker/`, 11 in `scripts/`, and 8 in the repository root (`.dockerignore`
and seven `requirements-*` files). None of them is Markdown. Preserve those historical bytes and records. Any intended replacement must be a separately reviewed, newly qualified artifact with its own hashes and signatures. Keep the original records
in `evaluation/` in place: a change breaks those records and the image build. Do not add any file, not even a README,
to `runtime/`, `contracts/` or `demo/`: `https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/scripts/verify-operations-image-qualification.py` lists every file in those
three folders, and the list must equal the inputs recorded in `evaluation/operations/restoration-qualification.json`
(the CI `agents` job fails otherwise). This map describes them instead.

## Product: the Agent Runtime Platform

| Path | What it is |
| --- | --- |
| `platform/core/src/agent_platform/` | The platform: front door (`app.py`), onboarding (`onboarding.py`), redaction client, audit, Kubernetes client, Secrets generator, and the Security & Operations Agent (`ops/`). |
| `platform/core/src/agent_platform/console.py` | Console data API (`/api/console/*`, read-only): topology, agents, onboarding guarantees, activity and Explain proofs. Design: `docs/console/design-spec.md`. |
| `platform/core/kubernetes/` | Manifests: namespaces, default-deny NetworkPolicies, RBAC, the ops agent's admission policy (`policies/admission.yaml`), quotas, workloads. |
| `platform/core/database/` | Platform SQL: the LiteLLM schema and the Financial Agent's `finance.sql` (row-level security, roles, sign-in lookup). |
| `platform/core/images/Dockerfile` | The app and ops images (distroless runtime, hash-locked Python sets). |
| `platform/core/ui/` | The console UI (Map, Agents, Onboard, Ops, Break it), served by `console.py`; own OFL fonts, no CDN. The Financial Agent UI shares its `style.css`, `core.js` and fonts byte-for-byte. |
| `platform/core/tests/` | Platform tests: manifest invariants, ops agent, approvals, onboarding, and policies against a real kube-apiserver (envtest). |
| `platform/agents/financial/` | **Financial Agent** (tenant #1): its own image, web app, read-only tools, grounding, sign-in. |
| `platform/agents/platform-guide/` | **Platform Guide** (tenant #2, Node.js): answers questions about the platform from a docs index bundled at build time; no data, one read-only `docs_search` tool. |
| `platform/clouds/gke/` | GKE: Terraform module, `render.py`, `images.json` (signed digests), `lifecycle.py` (`make up` / `down` / `fault` / `inventory`), `attack_suite.py`, `requalify.py`, `demo_check.py`, `demo_reset.py`, `corpus_live.py`, `passphrase.py`. |
| `providers/` | Model provider profiles. `make provider P=<name>` renders the gateway configuration and egress allowlist from one (`agent_platform/providers.py`); only active, owner-approved profiles render, and `make test` fails if the generated files drift. |
| `Makefile` | Entry points (listed at the top of the file): `test`, `test-policies`, `onboard`, `onboard-check`, `provider`, `plan`, `apply`, `up`, `down`, `port-forward`, `agent-forward`, `fault`, `attack`, `corpus-live`, `inventory`, `demo-check`, `seed-demo`, `demo-reset`, `secrets`, `passphrase-check`, `passphrase`. |
| `docs/agent-platform/` | Platform docs: claims matrix, model requalification, teardown plan. |
| `docs/agent-onboarding-contract.md`, `docs/agent-developer-guide.md` | How a team onboards an agent with one manifest. |
| `docs/evidence/` | Live evidence: requalification, onboarding, Financial Agent, attack-suite runs. |
| `docs/security/main-branch-protection.md`, `security-review-2026-10-13.md`, `known-limitations.md` | The `main` ruleset (applied), the security review and the accepted limitations. |
| `docs/security/claims-inventory.md`, `realistic-data-review-2026-10.md`, `realistic-data-corpus.md` | Every claim graded by its test; the realistic-data review and its fix PRs; the synthetic Saudi/bilingual corpus (`platform/core/tests/corpus/`). |
| `.github/workflows/agent-platform-images.yml` | Runs only after CI passes on `main`: build → Trivy → SBOM → push by digest → KEV gate → cosign → KMS attestation. |
| `.github/workflows/ci.yml`, `supply-chain.yml` | The required checks: `checks`, `agents`, `gitleaks`, `google-sdp-offline-evaluation`, `qualification`. |

## Shared code the product runs on

| Path | Used by the product for |
| --- | --- |
| `runtime/agents/` | Agent composition and controls (`controls.py`: the bounded injection assessor used by the Financial Agent's tools). Hash-bound; copied into the app and Financial Agent images. |
| `runtime/phase3/` | Trusted runtime types and the deterministic email redaction layer in front of the redactor. |
| `runtime/phase4/` | Prompt-injection assessment and tool-governance contracts. |
| `contracts/` | JSON Schema / OpenAPI contracts copied into the images. Hash-bound. |
| `demo/` | UI assets and synthetic fixtures copied into the app image. Hash-bound; the UI copy here is not served. |
| `evaluation/agent-composition/`, `evaluation/operations/` | Qualification inputs copied into images: the first into the app image (`platform/core/images/Dockerfile`), the second into the reused gateway image (`docker/agent-composition/Dockerfile`). |
| `docker/agent-composition/`, `docker/agent-database/`, `docker/google-sdp-context/` | Build definitions of the reused, qualified gateway, database and redactor images (pinned in `images.json`). |
| `scripts/` | Repository checks (`check.sh`, `validate.py`, `check-references.py`, `lint-repository.sh`), lock checks, the vulnerability policy evaluator and the KEV release gate. |
| `policy/` | The empty exception register used by the vulnerability policy. |
| `requirements-*.in` / `.txt` | Hash-locked dependency sets; each image installs only its own set. |
| `tests/` | Runtime, governance and supply-chain tests (`tests/agents`, `tests/phase3`–`phase5`). |

## History (kept as evidence; not part of the running platform)

| Path | What it was |
| --- | --- |
| `kubernetes/`, `k3s/` | Earlier sanitized Kubernetes templates and an API audit policy, before the GKE platform. `scripts/validate.py` still checks `kubernetes/` in CI. |
| `database/reference/` | Synthetic reference RLS schema and SQL behaviour checks. |
| `deploy/local-agents/` | Local two-agent composition used before the cluster. |
| `infra/gcp/` | Four Terraform units from earlier phases: `google-sdp-evaluation/` (the Google SDP evaluation bootstrap), `google-sdp-evaluation-cluster/`, `agent-synthetic-demo/` and `operations-synthetic-demo/`. Checked offline in CI. |
| `docker/google-sdp-evaluation/`, `docker/litellm-candidate/`, `docker/presidio-bounded/` | Evaluation and candidate images from earlier phases. |
| `evaluation/` (the rest) | Qualification records (hash-bound inputs and results) for the earlier phases. |
| `archive/qualification-history/` | Pointer to retired qualification history. |
| `docs/agents/`, `docs/phase3/`–`docs/phase5/`, most of `docs/security/` | Phase-by-phase design and execution records. |

## Request flow

Current proposed source flow (not live verified):

```text
browser → trusted Financial frontdoor (sign-in/session)
        → signed active capability → per-user Financial worker (u1/u2/u3)
        → trusted broker (fixed worker-key/user binding) → fixed read tools → PostgreSQL FORCE RLS
worker/app/Guide/Ops → trusted gateway boundary → mandatory redaction → private LiteLLM → provider
owner approval → trusted app signature → read-only Ops → independent executor → bounded Kubernetes patch
```

Financial workers have no database/session/signing credentials. Only the executor holds mutation RBAC; it independently verifies owner approval and consumes durable replay state. Agent grounding/history remain local code obligations. The Guide searches its build-time documentation index; old release subjects keep their historical index until a new qualified release.

The earlier claims and historical runbooks remain evidence of their original source and configuration; they do not establish live enforcement of this new source. The stock legacy `make up` path is blocked before cloud calls pending a target-bound reviewed cutover.

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
