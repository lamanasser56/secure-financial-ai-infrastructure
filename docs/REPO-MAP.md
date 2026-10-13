# Repository map

This page sorts the repository into the current product (the Secure AI Agent Platform), the shared code that product
runs on, and the history behind it. Start with **Product**. The **History** paths are kept as evidence and are not
part of the running platform.

Files under `runtime/`, `contracts/`, `demo/`, `evaluation/` and `scripts/` are bound by SHA-256 in the
qualification records under `evaluation/`. Do not move or rename them. A move breaks those records and the
image build.

## Product: the Secure AI Agent Platform

| Path | What it is |
| --- | --- |
| `platform/core/src/agent_platform/` | The platform: front door (`app.py`), onboarding (`onboarding.py`), redaction client, audit, Kubernetes client, Secrets generator, and the Security & Operations Agent (`ops/`). |
| `platform/core/kubernetes/` | Manifests: namespaces, default-deny NetworkPolicies, RBAC, the ops agent's admission policy (`policies/admission.yaml`), quotas, workloads. |
| `platform/core/database/` | Platform SQL: the LiteLLM schema and the Financial Agent's `finance.sql` (row-level security, roles, sign-in lookup). |
| `platform/core/images/Dockerfile` | The app and ops images (distroless runtime, hash-locked Python sets). |
| `platform/core/ui/` | The operations dashboard overlay (bilingual). |
| `platform/core/tests/` | Platform tests: manifest invariants, ops agent, approvals, onboarding, and policies against a real kube-apiserver (envtest). |
| `platform/agents/financial/` | **Financial Agent** (tenant #1): its own image, web app, read-only tools, grounding, sign-in. |
| `platform/agents/hello/` | **hello agent**: the smallest onboarded example (one manifest). |
| `platform/clouds/gke/` | GKE: Terraform module, `render.py`, `images.json` (signed digests), `lifecycle.py` (`make up` / `down` / `fault` / `inventory`), `attack_suite.py`, `requalify.py`. |
| `Makefile` | Entry points: `make test`, `make test-policies`, `make up`, `make attack`, `make down`, `make inventory`. |
| `docs/agent-platform/` | Platform docs: claims matrix, model requalification, teardown plan. |
| `docs/agent-onboarding-contract.md`, `docs/agent-developer-guide.md` | How a team onboards an agent with one manifest. |
| `docs/evidence/` | Live evidence: requalification, onboarding, Financial Agent, attack-suite runs. |
| `docs/security/main-branch-protection.md`, `security-review-2026-10-13.md`, `known-limitations.md` | The `main` ruleset (applied), the security review and the accepted limitations. |
| `.github/workflows/agent-platform-images.yml` | Runs only after CI passes on `main`: build → Trivy → SBOM → push by digest → KEV gate → cosign → KMS attestation. |
| `.github/workflows/ci.yml`, `supply-chain.yml` | The required checks: `checks`, `agents`, `gitleaks`, `google-sdp-offline-evaluation`, `qualification`. |

## Shared code the product runs on

| Path | Used by the product for |
| --- | --- |
| `runtime/agents/` | Agent composition and controls (`controls.py`: the bounded injection assessor used by the Financial Agent's tools). |
| `runtime/phase3/` | Trusted runtime types and the deterministic email redaction layer in front of the redactor. |
| `runtime/phase4/` | Prompt-injection assessment and tool-governance contracts. |
| `contracts/` | JSON Schema / OpenAPI contracts copied into the images. |
| `demo/` | UI assets and synthetic fixtures copied into the app image. |
| `docker/agent-composition/`, `docker/agent-database/`, `docker/google-sdp-context/` | Build definitions of the reused, qualified gateway, database and redactor images (pinned in `images.json`). |
| `scripts/` | Repository checks (`check.sh`, `validate.py`, `check-references.py`, `lint-repository.sh`), lock checks, the vulnerability policy evaluator and the KEV release gate. |
| `policy/` | The empty exception register used by the vulnerability policy. |
| `requirements-*.in` / `.txt` | Hash-locked dependency sets; each image installs only its own set. |
| `tests/` | Runtime, governance and supply-chain tests (`tests/agents`, `tests/phase3`–`phase5`). |

## History (kept as evidence; not part of the running platform)

| Path | What it was |
| --- | --- |
| `kubernetes/`, `k3s/` | Earlier sanitized Kubernetes templates and an API audit policy, before the GKE platform. |
| `database/reference/` | Synthetic reference RLS schema and SQL behaviour checks. |
| `deploy/local-agents/` | Local two-agent composition used before the cluster. |
| `infra/gcp/` | The Google SDP evaluation bootstrap (Terraform), qualified separately. |
| `docker/google-sdp-evaluation/`, `docker/litellm-candidate/`, `docker/presidio-bounded/` | Evaluation and candidate images from earlier phases. |
| `evaluation/` | Qualification records (hash-bound inputs and results) for the earlier phases. |
| `archive/qualification-history/` | Pointer to retired qualification history. |
| `docs/agents/`, `docs/phase3/`–`docs/phase5/`, most of `docs/security/` | Phase-by-phase design and execution records. |
| `providers/` | Model provider profiles; only active, owner-approved profiles render. |

## Where to start

1. `README.md` and this map.
2. `docs/agent-onboarding-contract.md`: what an onboarded agent inherits.
3. `platform/agents/hello/agent.yaml`, then `platform/agents/financial/`.
4. `platform/core/src/agent_platform/ops/`: the Security & Operations Agent.
5. `docs/evidence/`: what was tested live, and when.
