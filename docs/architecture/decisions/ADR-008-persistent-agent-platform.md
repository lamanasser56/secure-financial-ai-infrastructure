# ADR-008: Persistent on-demand private agent platform (Phase E)

- Status: **Accepted** (owner, 2026-10-10)
- Supersedes for Phase E: the per-window create/destroy lifetime of ADR-004 / ADR-005. Those ADRs remain the record for the
  synthetic SDP evaluation and for C.
- Related: ADR-001 (provider gateway), ADR-002 (tenant authority), ADR-003 (image promotion), ADR-006/007 (redaction).

## Context
- C proved the hardened GKE root and the in-cluster gateway/redactor/database stages: all 9 pre-channel stages passed live in four
  windows.
- C never completed its post-channel chain. Every failure came from operator ceremony outside the system: laptop/Cloud Shell
  tunnels, per-window 90/120-minute clocks, Cloud Shell token and quota limits, and worker SSH keys.
- The project goal is a reusable, tight, portfolio-grade platform where strictness is enforced by the system itself.

## Decision
1. One persistent private GKE cluster (`agent-platform`, zonal us-east1-b) built from a persistent variant of the C-proven root.
   - It has new resource names and a new state prefix, and no cleanup clock.
   - Its single node pool runs 1 node while working and **0 nodes when idle**.
2. **No public endpoint:** no LoadBalancer, NodePort, Ingress or node external IPs. Human access is only `kubectl port-forward` from the
   owner laptop through the IAM-gated control-plane DNS endpoint.
3. **Namespaces and trust boundaries:**
   - `platform`: gateway, redactor, Postgres with RLS. Only the gateway KSA has Workload Identity to the model provider.
   - `apps`: UI and the Financial Agent.
   - `ops`: the Security & Operations Agent.

   Default-deny ingress and egress everywhere; only declared paths are allowed. Provider egress is an FQDN allowlist on the gateway only.
4. **Enforcement in the system:**
   - NetworkPolicy, RBAC, Postgres RLS (non-owner role, no BYPASSRLS), and mandatory redaction before any model request.
   - A built-in ValidatingAdmissionPolicy limits the Ops Agent to restart, rollback and bounded scale of registered deployments.
   - Binary Authorization admits only signed image digests.
5. **Operations remediation:** observe → diagnose → propose → one-use owner approval (5 min, bound to request/target/evidence) →
   single execution with no retry → verification → audit. The model never approves or selects targets outside the catalog.
6. **Models through LiteLLM provider profiles** behind a stable internal alias, with pinned model versions. Only the approved
   profile is active: `gemini-3.5-flash`, `vertex_location: us` (US multi-region processing; no GA successor exists in
   us-east1 alone). Gateway key budgets total $10/month.
7. **No internet egress for nodes:** no Cloud NAT. Google APIs (Artifact Registry, Vertex, DLP, Logging) go through
   Private Google Access only. Every image runs from Artifact Registry by signed digest. NAT is added only if a
   non-Google provider profile is ever approved.
8. **Data:** synthetic only. The Postgres disk is retained, and snapshotted before each scale-down. Audit goes to a Cloud Logging sink.
9. **Lifecycle:** `make up` / `make test` / `make down`. The platform lives until the credit expiry (2026-11-08). Everything
   billable is torn down by ~2026-11-06, followed by a final inventory, and the durable proof stays in the repository.

## Consequences
- **Positive:**
  - No tunnels, worker adapters or per-window recovery.
  - Demos are repeatable in about 15 minutes.
  - Controls are testable as code (attack suite).
  - Idle cost is near zero with one cluster.
- **Negative / accepted:**
  - Some state persists between sessions: the cluster control plane, the PD and its snapshots, the IAM bindings and the Secrets.
    The security posture changes from "nothing remains" to "least privilege while idle".
  - The free-tier cluster fee covers only one zonal cluster, so masar-gke must be retired or paid for.
- **Idle-state invariant** (checked by `make test --idle`):
  - 0 nodes
  - no LoadBalancer, Ingress or external IP
  - Binary Authorization enforce on
  - gateway keys within budget or expired
  - no non-approved provider profile active
- **Superseded:** the worker-based D path (app on the worker, T1/T2/T3 tunnels, worker SSH key, per-window create/delete).
  C's evidence is kept as history and is not reported as passed.

## Out of scope
Service mesh, Vault, multi-cloud, any public endpoint, real data, Langfuse.
