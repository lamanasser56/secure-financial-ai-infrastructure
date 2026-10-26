# Agent onboarding contract

The current platform separates untrusted worker code from trusted model, data and mutation authorities. This contract describes current source behaviour; the [claims matrix](agent-platform/claims-matrix.md) determines what evidence supports a particular release.

## Platform-owned boundaries

| Boundary | Authority |
| --- | --- |
| Namespace and workload hardening | Generated namespaces, quotas, default-deny policies, restricted Pod Security, nonroot/read-only containers and no automatically mounted API token |
| Model path | Workers reach the mandatory redacting boundary with public scoped keys; the boundary alone holds the separate private LiteLLM credentials |
| Data path | The trusted Financial frontdoor routes an authenticated user to a bound worker; the broker verifies active user/agent capabilities and runs registered read-only tools under forced RLS |
| Mutation | The Ops observer proposes; an independent executor verifies owner approval, target/action/evidence bindings and current state before a bounded patch under RBAC/admission |
| Deployment | The selected release lock supplies deployment digests; image evidence and readiness must be checked for those exact subjects |

Client-side masking, worker output checks and worker-produced traces do not replace these boundaries. A worker is not trusted to choose another user's identity, bypass mandatory masking or grant itself mutation authority.

## Manifest

`platform/agents/<name>/agent.yaml` is validated by `agent_platform.onboarding`. Duplicate keys and unknown fields are refused. The actual working examples are the Financial and Platform Guide manifests; the [developer guide](agent-developer-guide.md) explains the commands.

| Field | Current rule |
| --- | --- |
| `agent`, `team`, `description`, `placement` | Name matches directory and accepted name grammar; bounded text; `placement: namespace` |
| `runtime` | Declared image alias, bounded command/port/replicas/resources; no platform-component image |
| `model` | `budget_usd_month` above zero, at most 5.00, within the declared platform model-key total |
| `redaction` | `required` |
| `tools` | Distinct registered read-only IDs/descriptions; write-like names refused |
| `data` | `none`, or the reviewed Financial broker shape; arbitrary extra data agents are refused |
| `operations` | Optional `observe` only; it grants no remediation opt-in |

The platform chooses namespace, network, identity, service type, model alias/provider and platform permissions. The manifest cannot request arbitrary egress, RBAC, host privileges, public services or provider credentials. A declared tool is not automatically implemented or proven safe: its dispatch/arguments and trusted broker path need current tests.

## Financial example

Financial has one logical UI and separate user-bound workers. Sign-in and expense entry live in `apps/financial-frontdoor`; they are not hosted in an untrusted worker. Workers have separate keys, no database/session/signing credentials and no direct Postgres path. Data access is mediated by the broker and forced RLS. The owner-facing alias `make agent-forward A=financial` reaches the trusted UI on `127.0.0.1:8081`.

## Guide example

The Guide has no finance data access. Its registered tool searches the documentation corpus bundled into its image. It uses the same mandatory model boundary. The current corpus is explicit and versioned; historical qualification records are not a fallback knowledge base.

## Evidence and limits

Test the current rendered manifests, real API-server permissions/admission, the actual broker identity path and both allowed/refused application behaviours. The live suite requires genuine exercise and healthy controls; missing exercise is not a pass. Run live mutations only in the approved final qualification scope.

Supported identifier patterns are masked; **person names and passport numbers are not masked**. Pattern matching depends on context and format. Per-process quotas/throttling and bounded request events are not durable global quotas or complete audit guarantees. See [known limitations](security/known-limitations.md).
