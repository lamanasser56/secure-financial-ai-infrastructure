# Architecture and trust boundaries

## Agent platform (Phase E, [ADR-008](architecture/decisions/ADR-008-persistent-agent-platform.md))

One private GKE cluster runs on demand (1 node while working, 0 when idle). Every control is enforced inside the system,
not by operator procedure.

```mermaid
flowchart LR
  owner([Owner laptop]) -- "kubectl port-forward 8080<br/>(IAM-gated DNS endpoint)" --> ui
  subgraph cluster [GKE agent-platform: private nodes, no LB/Ingress/external IP, no NAT, no internet egress]
    subgraph apps [ns apps: PSS restricted, default deny]
      ui[Front door: console + ops approval<br/>loopback only]
      fault[fault-demo target]
    end
    subgraph agents [ns agent-financial, agent-platform-guide: PSS restricted, default deny]
      fin[Financial Agent<br/>sign-in, read-only tools]
      guide[Platform Guide<br/>bundled docs, no data]
    end
    subgraph ops [ns ops]
      agent[Security & Operations Agent<br/>verify-only approval key]
    end
    subgraph platform [ns platform]
      redactor[Redactor<br/>SDP + deterministic email]
      gateway[LiteLLM gateway<br/>stable alias, per-agent keys, $10/month total]
      pg[(Postgres<br/>FORCE RLS, non-owner role)]
    end
    ui -- redact first --> redactor
    ui -- redacted text only --> gateway
    ui -- tenant-pinned read --> pg
    ui -- signed one-use approval --> agent
    owner -- "make agent-forward 8081 / 8082" --> agents
    fin -- redact first --> redactor
    fin -- redacted text only --> gateway
    fin -- "read-only role, FORCE RLS" --> pg
    guide -- redact first --> redactor
    guide -- redacted text only --> gateway
    agent -- "RBAC: read + patch named deployments<br/>VAP: rollout restart / bounded scale only" --> api[(kube-apiserver)]
    agent --> redactor
    agent --> gateway
    gateway --> pg
  end
  gateway -- "Workload Identity, FQDN allowlist<br/>PSC regional endpoint (private DNS)" --> vertex[[Vertex AI gemini-3.5-flash<br/>us multi-region]]
  redactor -- "Workload Identity, FQDN allowlist<br/>PSC regional endpoint (private DNS)" --> dlp[[Sensitive Data Protection]]
  ci[[GitHub Actions: Trivy, SBOM,<br/>keyless cosign, KMS attestation]] -. signed digests .-> ar[(Artifact Registry)]
  ar -. Binary Authorization .-> cluster
```

| Boundary | Enforced by | Evidence |
|---|---|---|
| No public exposure | private nodes and endpoint; no LB/Ingress; quota `services.loadbalancers: 0` | render invariants (`make test`), live attack suite |
| No internet egress | no Cloud NAT and no external IPs; Google APIs via Private Google Access, and the two `rep.googleapis.com` endpoints (Vertex `us`, SDP `us-east1`), which Private Google Access does not serve, via Private Service Connect regional endpoints with private DNS zones (`private_endpoints.tf`) | Terraform plan; live chain check pending (see [claims matrix](agent-platform/claims-matrix.md)) |
| Namespace isolation | default-deny NetworkPolicies + explicit paths; FQDN egress only for gateway (Vertex) and redactor (DLP) | render invariants, live attack suite (direct egress blocked) |
| Workload hardening | Pod Security "restricted" in every namespace; nonroot, read-only root, no capabilities | `make test-policies` (real kube-apiserver), render invariants |
| Tenant isolation | Postgres FORCE ROW LEVEL SECURITY; app role non-owner, NOBYPASSRLS; tenant set server-side | bootstrap contract check, live attack suite (cross-tenant read) |
| Redaction before any model call | the platform client libraries (`RedactorClient`; `clients.js` in the Platform Guide) raise on any redaction failure, so they never call the gateway. Not enforced at the gateway: an agent's NetworkPolicy also allows the gateway, and the gateway does not check redaction ([known limitations](security/known-limitations.md)) | unit tests, live attack suite (redactor down → 0 spend) |
| Ops agent authority | RBAC (read + patch named deployments) and a ValidatingAdmissionPolicy (rollout restart and bounded scale only; the Pod template may change only by the restart annotation, so no command, args, env, envFrom, resources, probes, image or label change, even if the agent identity is compromised; no rollback) | `make test-policies`: allowed and denied cases on a real API server |
| Human approval | Ed25519 one-use tokens signed only by the front door (owner passphrase); the agent holds only the public key | unit tests (binding, expiry, replay, forgery, restart) |
| Supply chain | Trivy + SBOM + keyless cosign in CI; Binary Authorization with a KMS attestor rejects unattested digests | CI receipts, live attack suite (unsigned image rejected) |
| Model text and logs | treated as data: diagnosis is deterministic; explanations are redacted, display-only and cannot change targets or actions | unit tests (log-planted instruction), live attack suite |

Cloud specifics live behind a contract in `platform/clouds/gke`. See the [porting guide](porting-guide.md); portability is
documented, not tested.

## Reference control path (unchanged, reused by the platform)

The reference runtime enforces the sequence in `runtime/phase3/trusted_runtime.py`:

- Authentication derives identity, and the tenant resolver derives tenant context from trusted claims. Caller-supplied tenant fields are rejected.
- Authorization and policy must succeed before redaction or LiteLLM is called.
- The runtime consumes a provider-neutral redaction result.
- The sole concrete Presidio adapter validates Analyzer spans and verifies protected fragments are absent from Anonymizer output before returning that result.
- Provider output must satisfy the closed structured result shape.
- Any failed control stops the sequence and emits a sanitized failure category.

Phase 4 provides a registry and a governance coordinator for tool requests:

- Tool metadata binds an action, risk class, schemas, limits and approval requirement.
- Unknown or disabled tools fail closed.
- Prompt-injection assessment, policy and verified human approval are explicit boundaries before any execution.
- Audit events use a closed schema and exclude raw prompts, arguments, credentials and tenant identifiers.

The platform composes these unchanged agent cores (`IntegratedCore`, `TenantDatabaseTools`, `DeterministicEmailRedactor`) with in-cluster transports.

This repository is a portfolio reference implementation with synthetic data only. Each claim is classified in the [claims
matrix](agent-platform/claims-matrix.md); the [claims inventory](security/claims-inventory.md) grades the test behind each claim.
