# AI Infrastructure and Secure Agent Platform

A standalone portfolio repository of infrastructure and secure AI runtime work adapted from my contribution to the private MASAR team project. It contains no product frontend, backend, database schema, customer data, deployment credentials, or original Git history. The examples use synthetic requests and an `ai-platform` namespace.

The repository demonstrates a fail-closed route from a trusted application boundary through authentication, tenant context, authorization, input validation, policy, Presidio redaction, LiteLLM, and output validation. It also contains Kubernetes isolation templates, a metadata-only API audit policy, schema contracts, and CI validation.

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

- Python reference runtime with ordered, fail-closed controls, Presidio and LiteLLM HTTP adapters, sanitized trace envelopes, and synthetic qualification tests.
- Tool registry, invocation, policy, prompt-injection assessment, approval verification, and audit-event contracts. The governance coordinator produces an eligible invocation; it does not execute a product tool.
- JSON Schema and OpenAPI contracts for runtime and tool boundaries.
- Kubernetes manifests for namespace quotas, restricted Pod Security Admission, default-deny network policy, DNS allowance, Presidio, and LiteLLM. The manifests are sanitized templates; repository validation parses them and checks their composition.
- Kubernetes API audit policy that records metadata without request or response bodies.
- CI with read-only checkout, runtime tests, schema and YAML validation, source-scope checks, and Git history secret scanning.

### Designed

- Observability requirements and sensitive-data limits in [Observability](docs/observability.md). There is no claimed Prometheus or Grafana deployment in this repository.
- Supply-chain controls and promotion gates in [Supply chain](docs/supply-chain.md). Image scanning, SBOM generation, signing, and deployment are described as gates, not represented as completed by this standalone CI.
- Cloud identity, secret ownership, alert routing, retention, backup, and recovery boundaries in [Operations](docs/operations.md).

### Integration-dependent

- A product-owned authenticator, tenant resolver, authorizer, tool executor, and audit sink must be supplied and tested against a real application. The included mocks are only synthetic test fixtures.
- Set an approved provider model, GCP project, region, and Workload Identity binding; inject the LiteLLM master key from an external secret manager. The placeholders deliberately block direct deployment.
- Requalify image digests and vulnerability state, CNI NetworkPolicy behavior, DNS and egress, namespace quota, probes, monitoring access, and cluster audit configuration in the target environment.
- Production deployment, live provider use, customer-data processing, alert delivery, and end-to-end tenant isolation require separate integration evidence.

## Repository layout

| Path | Purpose |
| --- | --- |
| `runtime/phase3/` | Trusted AI path and HTTP adapters |
| `runtime/phase4/` | Governed tool contracts and audit boundary |
| `contracts/` | JSON Schema and OpenAPI definitions |
| `tests/` | Synthetic runtime and governance qualification |
| `kubernetes/` | Namespaced security and AI service templates |
| `k3s/` | Metadata-only Kubernetes API audit policy |
| `.github/workflows/` | Validation-only CI |
| `docs/` | Architecture, observability, supply-chain, and operations notes |

## Run locally

Use Python 3.12 or newer. From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
bash scripts/check.sh
kubectl kustomize kubernetes/base  # optional manifest rendering check
```

The tests use synthetic fixtures and local loopback HTTP servers. They do not need cloud credentials or a running Kubernetes cluster. Rendering manifests does not configure Workload Identity or authorize deployment; see [Operations](docs/operations.md).

## Security and attribution

Do not commit `.env` files, live keys, tokens, customer data, private endpoints, cloud project IDs, or real service-account addresses. Run `bash scripts/check.sh` and a current secret scanner before every publication. CI runs Gitleaks against Git history. The published history starts with this sanitized extraction and does not import MASAR commits.

The Python runtime, contracts, infrastructure manifests, and qualification fixtures were adapted from my MASAR AI Infrastructure contribution. MASAR was a team project; its product frontend and backend remain with their original contributors. Public third-party images and GitHub Actions retain their upstream names and version or digest references. This repository makes no claim of ownership of those upstream projects.

See [Architecture](docs/architecture.md) for the trust boundary and [Operations](docs/operations.md) for deployment prerequisites.
