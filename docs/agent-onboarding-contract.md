# Agent Runtime Platform onboarding contract

**RC1 source status:** see [the trusted-boundary migration](releases/rc1-boundary-migration.md). The new source is not deployed; historical images and live claims do not verify it. Current Financial UI access moves to the trusted `apps/financial-frontdoor` Service after an authorized cutover. Do not run historical lifecycle commands for assessment provisioning.

The product is the platform. A team brings an agent, and the agent inherits the platform's security controls. The
team does not rebuild them. This page states what the platform guarantees, what an agent must provide, and what an
agent must never do. An agent that does not meet the contract is not deployed.

**Status:** this contract describes the platform as designed. A control counts as live-tested only when the
[claims matrix](agent-platform/claims-matrix.md) says so. Onboarding is implemented by `make onboard`; see the
[developer guide](agent-developer-guide.md). Three agents are declared today:

- the **Security & Operations Agent** (an example of governed operational automation);
- the **Financial Agent**, tenant #1 (`platform/agents/financial/agent.yaml`, namespace `agent-financial`, its own image);
- the **Platform Guide**, tenant #2 (`platform/agents/platform-guide/agent.yaml`, namespace `agent-platform-guide`, Node.js, no data).

## 1. Proposed RC1 platform boundaries

These are the **new source/deployment contract**, not claims about the seven historical images or the original cluster. Focused local tests cover protocols and a disposable PostgreSQL server; GKE admission, packets, deployed credentials and artifact contents remain NOT VERIFIED. The forty-case live assessment is still pending authorization and safety gates.

| Boundary | Enforced outside a hostile worker in the proposed release | Remaining verification |
| --- | --- | --- |
| Mandatory model redaction | `gateway_boundary.py` authenticates each external key, redacts all accepted text messages and forwards using a different private LiteLLM key. Workers cannot select a provider URL, stream or unsupported request surface. | Qualified images, legacy-key revocation and actual CNI/private-port denial before live use. |
| User/tenant data access | Financial sign-in and session/capability signing live in `apps/financial-frontdoor`. Workers receive public verification material and per-user worker/broker credentials, never DB URLs or signing keys. Broker identity must match both the active signed capability and the fixed user bound to that worker key; caller UUIDs cannot select it. | New DB migration and effective runtime credentials/policies. A compromised trusted broker is outside this worker threat model. |
| Database least privilege | Fresh `finance_frontdoor` and `finance_data_broker` roles separate login/write and read-tool access. Legacy worker/web roles are disabled and revoked. GUC selection occurs only inside the trusted broker. | PostgreSQL 16.2 local permission tests do not establish production PostgreSQL 17 state. |
| Tool access | The broker exposes only the three existing read tools with strict arguments and fixed SQL. No SQL/identity override field is accepted. Data-none workloads receive no broker capability. | New data workloads need a separately reviewed trusted user-authentication route; registration alone does not mint capabilities. |
| Human-approved mutation | `ops-agent` retains read-only API grants. A separate `ops-executor` verifies owner signatures/binding/fresh evidence and consumes nonces durably before a single bounded patch. Admission explicitly denies Ops writes and bounds executor writes. | Real API authorization/CEL, replay-volume lifecycle and qualified executor image. |
| Network and workloads | Default-deny, DNS and named service/port paths; no direct agent SQL/private-provider egress, provider identity or Kubernetes token. Restricted nonroot workloads, resource quotas and no public Services remain declared. | Live CNI/PSA/egress enforcement. |
| Supply chain | Historical pins/signatures are preserved. New source requires new qualified subjects and unchanged enforced Binary Authorization. The renderer rejects historical locks for this deployment contract. | New digest/source/scan/SBOM/signature/attestation evidence and actual admission; no builds authorized yet. |
| Audit | Trusted mediators emit their own bounded request/caller/data/approval events. Worker traces are not an independent authority. | Cloud sink authenticity, completeness and failure/durability still need live testing. |

Agent-local model decisions, answer grounding, prompt-injection filters, history and per-user counters remain agent-code obligations. Service-side limits bound keys and workers, but no durable platform-enforced per-user token/DLP ceiling is claimed. Each Financial user has a separate worker Deployment/Secret and broker key. A genuine foreign-user capability is rejected by the broker's fixed key/user mapping. The current three synthetic users use opaque slots u1–u3; provisioning additional data workloads/users requires reviewed routes, credentials and resource bounds.

## 2. What an agent must provide

1. **An agent manifest** (reviewed in the PR that onboards the agent):
   - name and namespace;
   - the model alias and the per-agent monthly budget (USD);
   - the tool registry entries: ID, argument and result schemas, risk class, limits, and approval requirement;
   - its data access: broker tool scopes and the trusted user-authentication/capability issuer; no worker Postgres role;
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
- Treat local redaction as proof of trusted gateway enforcement. The gateway redacts accepted text independently.
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
5. A reviewed v2 cutover bundle must install qualified images, fresh mediator credentials, per-user routes and the DB/RBAC/network migration. Legacy `make up` is blocked before cloud calls; it is not a safe migration.
6. A live run proves the agent's attack tests and one end-to-end turn. Its claims enter the claims matrix as
   live-tested only after that run passes.

## 5. Known limitations every agent inherits

- **Person names are not redacted.** The qualified redaction entity set has no person-name category, so a name in a
  question reaches the model provider as written. Agents must not rely on name redaction.
- The [historical trust model](security/known-limitations.md#trust-model-the-agents-code-is-trusted) describes the old runtime. The new source moves model/data/mutation authority out of workers; answer grounding and counters remain agent-local.
- **Passport numbers are not masked** (INFO-7 in the [known limitations](security/known-limitations.md)).
- One cluster and one model alias. Portability to other clouds is documented, not tested
  ([porting guide](porting-guide.md)).
- Synthetic data only.

## 6. Reference consumer: the Financial Agent

The Financial Agent (`platform/agents/financial/`, tenant #1) is the reference consumer. The [13 October claims](agent-platform/claims-matrix.md) concern the historical runtime, not this migration. In the proposed source:

- **Data:** users add and list their own expenses through the trusted frontdoor's web API (`user_entry: own-rows` in its
  manifest). Rows are protected by RLS keyed to the signed-in user.
- **Authentication:** three local users, argon2id password hashes, and a signed session cookie.
- **Agent access:** the assistant is read-only: its three registered tools run read-only queries on the same table,
  through the capability-checked broker; workers hold no database role. Onboarding refuses a tool that is not `access: read` or whose ID looks like a write.
- **Numeric grounding:** syntactic checks cover recorded numeric/monetary cases; arbitrary semantic grounding is not established.
- **Conversation history:** kept server-side, never supplied by the client.
- **Limits:** a per-user rate limit and token budget.
- **Audit:** bounded worker turn traces plus independent mediator events; durable completeness is not established.
- **Attack tests:** cross-user access, "show Sara's expenses", and injection through user-entered expense names.
