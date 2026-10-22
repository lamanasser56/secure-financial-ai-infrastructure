# Threat model

Statuses as of attack-suite run 6 (2026-10-19, 19/19, [attack-suite.json](../evidence/attack-suite.json)). Case names
are the attack-suite cases graded in the [claims inventory](claims-inventory.md); accepted gaps are in
[known limitations](known-limitations.md).

| Threat | Boundary | Control | Status and evidence |
| --- | --- | --- | --- |
| Cross-user or cross-tenant disclosure | User → agent → Postgres | User ID from the signed session only; FORCE ROW LEVEL SECURITY; non-owner, NOBYPASSRLS, read-only agent role | Live-tested: `financial_cross_user_database`, `financial_cross_user_api_and_forged_session`, `financial_show_saras_expenses`; [Financial Agent live run](../evidence/financial-agent-live-2026-10-13.json) |
| Prompt or tool injection | Untrusted text → model → tools | Read-only tool registry, closed decision shape, instruction-like user data withheld, numeric grounding | Live-tested with narrow inputs: `financial_prompt_injection_in_question`, `financial_filter_bypass_merchant_stays_grounded`, `ops_log_injection_adds_no_action_and_no_text`; realistic inputs offline ([realistic-data review](realistic-data-review-2026-10.md)) |
| Direct internet or provider access | Workload → internet or model provider | No Cloud NAT, no external IPs; Vertex AI and Sensitive Data Protection only through Private Service Connect; FQDN egress only for the gateway and the redactor | Live-tested: `egress_containment`; [requalification](../evidence/requalification.json) |
| Protected content in telemetry | Runtime → logs and audit | Closed audit schemas; content fields refused by `audit.emit` | Offline tests; live `no_secrets_in_env_or_logs` scans for credentials only, not personal data |
| Secret theft | Git, Pods, cloud identity | Secrets mounted as files; Workload Identity only for the gateway and the redactor; gitleaks on full history | Live-tested: `no_secrets_in_env_or_logs`; gitleaks is a required check ([branch protection](main-branch-protection.md)) |
| Supply-chain compromise | Source → image → cluster | Trivy gate, SBOM, KEV gate, keyless cosign, Cloud KMS attestation; Binary Authorization admits attested digests only | Live-tested: `unsigned_image_rejected`; an image signed by another key is not tested |
| Ops agent misuse | Ops agent → Kubernetes API | RBAC, the `ops-agent-bounded-remediation` admission policy, one-use owner approvals bound to resourceVersion | Live-tested in part: `ops_agent_cannot_change_onboarded_agents`, `ops_stale_approval_refused`; template denials on a real kube-apiserver (envtest) ([claims matrix](../agent-platform/claims-matrix.md)) |
| Public exposure | Internet → cluster | Private nodes and endpoint; no LoadBalancer, NodePort or Ingress (quota) | Live-tested: `no_public_exposure` |
| Recovery failure | Cluster, database, storage | Postgres snapshot at `make down` only | Not tested: no schedule and no restore drill ([known limitations](known-limitations.md)) |

## Boundary: a hostile onboarded agent

An onboarded agent's code is trusted for the controls that run inside it
([trust model](known-limitations.md#trust-model-the-agents-code-is-trusted)). Against an agent whose code is hostile:

| Threat | Control | Status and evidence |
| --- | --- | --- |
| Leave its namespace: internet, model provider, Kubernetes API, metadata server, other platform services | Default-deny NetworkPolicies, no NAT, no API token, Pod Security restricted | Live-tested from the agent pod: `egress_containment` (and the [hello onboarding run](../evidence/onboarding-hello-live-2026-10-12.json)) |
| Run an unsigned image or gain privileges | Binary Authorization; Pod Security restricted | Live-tested: `unsigned_image_rejected`; Pod Security on a real kube-apiserver (envtest) |
| Spend beyond its key | Per-agent gateway key: one alias, monthly budget, 20 requests per minute, 2 parallel | Offline tests; the budget was never exhausted live ([claims inventory](claims-inventory.md), G4) |
| Send unredacted text to the model provider | None outside the agent: the gateway does not check redaction | **Open**, accepted limitation |
| Read another data agent's users and rows | None: every data agent gets the same database roles, and RLS trusts the user ID the caller sets | **Open**; only one data agent exists today |
| Skip its own tool governance, output admission, per-user ceilings or audit | None: these run in the agent's code | **Open** by design of the current platform |
| Exhaust shared Postgres, redactor or gateway capacity | Gateway key rate limits only; no per-agent connection limits | **Open**; the gateway's behaviour under a connection flood is unverified |
| Exfiltrate data through DNS queries | kube-dns is reachable | **Unverified**: the egress probe tests TCP connect only |

Residual risks: the hostile-agent gaps above, person names and passport numbers not masked, detector accuracy
on real-world text, provider data handling, per-user ceilings kept in memory, no Data Access audit logs, and no alerts
or restore drill. Each is recorded in [known limitations](known-limitations.md).
