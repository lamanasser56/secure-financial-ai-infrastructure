# Agent onboarding contract

The product is the platform. A team brings an agent, and the agent inherits the platform's security controls. The
team does not rebuild them. This page states what the platform guarantees, what an agent must provide, and what an
agent must never do. An agent that does not meet the contract is not deployed.

**Status:** this contract describes the platform as designed. A control counts as live-tested only when the
[claims matrix](agent-platform/claims-matrix.md) says so. Onboarding is implemented by `make onboard`; see the
[developer guide](agent-developer-guide.md). Two agents are declared today:

- the **Security & Operations Agent** (the flagship, a platform component);
- the **Financial Agent**, tenant #1 (`platform/agents/financial/agent.yaml`, namespace `agent-financial`, its own image).

## 1. What every agent inherits

| Control | How the platform enforces it | What the agent does about it |
|---|---|---|
| No public exposure | Private nodes, no load balancer, Ingress or external IP. Users reach the front door through an IAM-gated port-forward. | Nothing. The agent listens on loopback or a cluster-internal port only. |
| No internet egress | No NAT and no external IPs. Only the gateway (model provider) and the redactor (Sensitive Data Protection) have FQDN egress, through Private Service Connect. | Nothing. Any other outbound call fails. |
| Identity | The front door authenticates the user. The agent receives a verified identity (subject, tenant) from trusted claims. | Uses the verified identity only. Rejects user or tenant IDs that arrive in the request body or prompt. |
| Redaction before any model call | The redactor runs first and fails closed: if it fails, no model request is sent. | Sends model text only through the platform redaction client. |
| Model access | One stable alias (`secure-financial-chat`) behind the LiteLLM gateway, with a per-agent key and a monthly budget. Provider credentials stay in the gateway (Workload Identity). | Calls the alias with its own key. Never holds a provider key and never names a provider model. |
| Output admission | Model output must match a closed, schema-validated decision shape. Native tool calls, thought text and images are rejected. | Defines its decision schema. Treats model text as data, never as instructions. |
| Tool governance | Each tool is registered with an ID, argument schema, risk class, limits and approval requirement. Unknown or disabled tools fail closed. The core dispatches tools; the model only proposes them. | Registers every tool. Ships no tool that reaches outside its registered scope. |
| Tenant data isolation | Postgres FORCE ROW LEVEL SECURITY. Each agent gets a non-owner, NOBYPASSRLS role. The tenant and user are set server-side per transaction. | Reads through its role only. Never builds SQL from model output. |
| Human approval for changes | Ed25519 one-use approval tokens signed by the front door after the owner enters their passphrase. The agent holds only the verify key. | Marks state-changing tools as approval-required. |
| Workload hardening | Pod Security "restricted": nonroot, read-only root filesystem, no capabilities, default-deny NetworkPolicies. | Builds an image that runs under these settings. |
| Supply chain | Trivy (HIGH/CRITICAL gate), SBOM, keyless cosign and a KMS attestation in CI. Binary Authorization rejects unattested digests. | Builds through the platform image pipeline and is deployed by digest. |
| Audit | Closed-schema audit events with no prompts, arguments, credentials or raw tenant IDs. | Emits the platform's audit events. Adds no free-text logging of user or model content. |

## 2. What an agent must provide

1. **An agent manifest** (reviewed in the PR that onboards the agent):
   - name and namespace;
   - the model alias and the per-agent monthly budget (USD);
   - the tool registry entries: ID, argument and result schemas, risk class, limits, and approval requirement;
   - its data access: tables, the Postgres role, and the RLS policies the role depends on;
   - the per-turn limits: model requests, tool executions, and seconds.
2. **A decision schema** for model output. The model proposes; the agent's core validates and acts.
3. **A container image** built by the platform pipeline from this repository.
4. **Attack tests** for its own boundaries. At minimum:
   - cross-user and cross-tenant access;
   - prompt injection, including through data the agent itself reads back;
   - a forbidden tool and an unregistered tool;
   - redactor-down (expect no model request and no spend).

## 3. What an agent must never do

- Call a model provider directly, or hold a provider credential.
- Send unredacted text to the gateway.
- Take the tenant or user identity from the prompt, the request body, or model output.
- Execute model output as code, SQL, a shell command or a tool call that has not been validated.
- Log prompts, model text, tool arguments or credentials.
- Open egress, expose a Service outside the cluster, or request RBAC beyond its namespace.
- Write to data it was given read-only access to.

## 4. Onboarding steps

1. Write `platform/agents/<name>/agent.yaml` (closed fields; see the developer guide).
2. Run `make onboard A=<name>`. It refuses the manifest with a reason, or it generates the namespace, network,
   quota, workload and platform-side access into `platform/core/kubernetes/agents/`.
3. Open a PR with the manifest, the generated files and the agent's attack tests. CI runs the unit tests, the
   rejection tests, the render invariants and the policy tests on a real kube-apiserver.
4. The owner reviews any IAM, network or Terraform change shown as a diff; nothing is applied without approval.
5. After the merge, `make up` deploys by signed digest and creates the agent's keys without rotating others.
6. A live run proves the agent's attack tests and one end-to-end turn. Its claims enter the claims matrix as
   live-tested only after that run passes.

## 5. Known limitations every agent inherits

- **Person names are not redacted.** The qualified redaction entity set has no person-name category, so a name in a
  question reaches the model provider as written. Agents must not rely on name redaction.
- One cluster and one model alias. Portability to other clouds is documented, not tested
  ([porting guide](porting-guide.md)).
- Synthetic data only.

## 6. Reference consumer (planned)

This sample Financial Agent will be written from scratch for this repository and will prove the contract end to end:

- **Data:** users enter their own expenses (add and list). Rows are protected by RLS keyed to the signed-in user.
- **Authentication:** two or three local users, argon2 password hashes, and a signed session cookie.
- **Agent access:** read-only queries on the same table, through its own role.
- **Numeric grounding:** every number in a reply must match a number from this turn's tool results.
- **Conversation history:** kept server-side, never supplied by the client.
- **Limits:** a per-user rate limit and token budget.
- **Audit:** one audit event per turn.
- **Attack tests:** cross-user access, "show Sara's expenses", and injection through user-entered expense names.
