# AI Infrastructure and Secure Agent Platform

A standalone portfolio repository of infrastructure and secure AI runtime work adapted from my contribution to the private MASAR team project. It contains no product frontend or backend, authoritative product schema, customer data, deployment credentials, or original Git history. Its database schema is a synthetic, reference-only RLS fixture. The examples use synthetic requests and an `ai-platform` namespace.

The repository demonstrates a fail-closed route from a trusted application boundary through authentication, tenant context, authorization, input validation, policy, Presidio redaction, LiteLLM, and output validation. It also contains Kubernetes isolation templates, a metadata-only API audit policy, schema contracts, and CI validation.

The [documentation index](docs/README.md) restores the architecture decisions, phase contracts, security model, and operations runbooks in sanitized form.

```text
Application-owned identity and tenant adapters
    → trusted runtime controls
    → Presidio Analyzer + Anonymizer
    → LiteLLM gateway
    → approved provider integration
    → structured output validation + sanitized audit event
```

## Status

### Implemented

- Two bounded read-only [demo agents](docs/agents/README.md), shared canonical runtime/governance composition, separate tenant/profile controls, offline CLIs and a private Arabic RTL / English LTR free-text conversation UI. Authentication, model responses and Presidio service doubles are explicitly simulated; no live provider result is claimed.

- Python reference runtime with ordered, fail-closed controls, Presidio and LiteLLM HTTP adapters, sanitized trace envelopes, and synthetic qualification tests.
- Tool registry, invocation, policy, prompt-injection assessment, approval verification, and audit-event contracts. The governance coordinator produces an eligible invocation; it does not execute a product tool.
- JSON Schema and OpenAPI contracts for runtime and tool boundaries.
- Kubernetes manifests for namespace quotas, restricted Pod Security Admission, default-deny network policy, DNS allowance, ServiceAccount hardening, Presidio, and LiteLLM. Separate examples cover scoped RBAC, migration credentials, NodeLocal DNS, storage, and backup. The manifests are sanitized templates; repository validation parses them and checks their composition.
- Kubernetes API audit policy that records metadata without request or response bodies.
- A reference-only PostgreSQL schema with `FORCE ROW LEVEL SECURITY`, distinct migration and runtime role expectations, and behavioral tests for missing and cross-tenant context.
- Reusable Trivy, OSV-Scanner, Syft, Cosign, Gitleaks, repository lint, and exact-subject vulnerability-policy qualification. The supply-chain workflow uses a public digest-pinned image and synthetic signing key; it does not release a portfolio image.
- CI with read-only checkout, runtime and security tests, schema and YAML validation, source-scope and documentation-link checks, repository lint, Git history secret scanning, and a separate supply-chain qualification workflow.

### Designed

- Observability requirements and sensitive-data limits in [Observability](docs/observability.md). There is no claimed Prometheus or Grafana deployment in this repository.
- Production image build, registry publication, provenance verification, signing-key custody, and deployment promotion in [Supply chain](docs/supply-chain.md).
- Cloud identity, secret ownership, alert routing, retention, backup, and recovery boundaries in [Operations](docs/operations.md).

### Integration-dependent

- Live demo-agent identity, real Presidio qualification and scoped LiteLLM/Gemini integration require the separate [live integration gates](docs/agents/live-integration.md). No live model call or provider credential is enabled by the demo.

- A product-owned authenticator, tenant resolver, authorizer, tool executor, and audit sink must be supplied and tested against a real application. The included mocks are only synthetic test fixtures. Product-table RLS coverage must be qualified separately against the authoritative schema.
- Set an approved provider model, GCP project, region, and Workload Identity binding; inject the LiteLLM master key from an external secret manager. The placeholders deliberately block direct deployment.
- Requalify image digests and vulnerability state, CNI NetworkPolicy behavior, DNS and egress, namespace quota, probes, monitoring access, and cluster audit configuration in the target environment.
- Production deployment, live provider use, customer-data processing, alert delivery, and end-to-end tenant isolation require separate integration evidence.

## Repository layout

| Path | Purpose |
| --- | --- |
| `runtime/phase3/` | Trusted AI path and HTTP adapters |
| `runtime/phase4/` | Governed tool contracts and audit boundary |
| `runtime/agents/` | Bounded shared agent coordinator and offline entry points |
| `demo/` | Own synthetic fixtures and private UI assets |
| `contracts/` | JSON Schema and OpenAPI definitions |
| `tests/` | Synthetic runtime and governance qualification |
| `kubernetes/` | Namespaced security and AI service templates |
| `database/reference/` | Synthetic, reference-only RLS schema and SQL behavior checks |
| `policy/` | Empty exception register for fail-closed image policy |
| `scripts/` | Validation, linting, and portable supply-chain qualification |
| `k3s/` | Metadata-only Kubernetes API audit policy |
| `.github/workflows/` | Source validation and public-input supply-chain qualification |
| `docs/` | Architecture, observability, supply-chain, and operations notes |

## Run locally

Use Python 3.12 or newer. From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
bash scripts/check.sh
kubectl kustomize kubernetes/base
bash scripts/lint-repository.sh
bash scripts/scan-secrets.sh  # requires Gitleaks 8.30.1
```

The tests use synthetic fixtures and local loopback HTTP servers. They do not need cloud credentials or a running Kubernetes cluster. To run the live RLS behavior checks, provide a disposable PostgreSQL database named `portfolio_rls_test` through `PORTFOLIO_TEST_DATABASE_URL` and install `psql`; `scripts/check.sh` runs them automatically when both are available. The [supply-chain qualification](docs/supply-chain.md) requires pinned scanners and network access. Rendering manifests does not configure Workload Identity or authorize deployment; see [Operations](docs/operations.md).

## Private agent demonstration

```bash
python3 -B scripts/diagnose-infrastructure.py --scenario archive-export
python3 -B scripts/analyze-demo-expenses.py --period 2026-01
python3 -B scripts/serve-demo-agents.py
```

Open `http://127.0.0.1:8765`. This is an offline synthetic simulation with simulated authentication. The server binds only to loopback; do not expose it publicly or enter real data. See the [agent guide](docs/agents/README.md) for startup identity selection, limits and evidence boundaries.

## Security and attribution

Do not commit `.env` files, live keys, tokens, customer data, private endpoints, cloud project IDs, or real service-account addresses. Run `bash scripts/check.sh` and a current secret scanner before every publication. CI runs Gitleaks against Git history. The published history starts with this sanitized extraction and does not import MASAR commits.

The Python runtime, contracts, infrastructure manifests, and qualification fixtures were adapted from my MASAR AI Infrastructure contribution. MASAR was a team project; its product frontend and backend remain with their original contributors. Public third-party images and GitHub Actions retain their upstream names and version or digest references. This repository makes no claim of ownership of those upstream projects.

See [Architecture](docs/architecture.md) for the trust boundary and [Operations](docs/operations.md) for deployment prerequisites.
