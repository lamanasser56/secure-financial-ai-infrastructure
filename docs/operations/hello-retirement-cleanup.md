# One-time cleanup after removing the hello agent (owner approval required)

> **Completed.** Verified by `make demo-check` on 22 Oct 2026: namespace `agent-hello` gone, NetworkPolicies
> `platform/agent-hello-to-gateway` and `platform/agent-hello-to-redactor` gone, and the key alias `agent-hello` gone
> from Secrets `platform/bootstrap` and `platform/redactor`. The gateway's spend history can still list the retired
> alias `agent-hello` (run 6, `docs/evidence/attack-suite.json`); that is history, not a live key. The page below is
> kept as the record of the plan.

Merging the hello removal changes the repository only. `make up` applies manifests with `kubectl apply --server-side` and **no `--prune`**, so nothing that was removed from source is deleted from the cluster. The steps below were the plan (now completed; see the note above).

## What remains in the live cluster

| Where | What | Effect |
| --- | --- | --- |
| namespace `agent-hello` | Namespace, ResourceQuota, LimitRange, ServiceAccount, Deployment `agent`, Service, NetworkPolicies `default-deny`, `allow-dns`, `agent`, Role/RoleBinding `ops-agent-observe`, Secret `agent` (its two keys) | The pod still starts on the next `make up` (replicas 1) and holds a live gateway key. |
| namespace `platform` | NetworkPolicies `agent-hello-to-gateway`, `agent-hello-to-redactor` | Ingress to the gateway and redactor stays open for a namespace that no longer has source. |
| Secret `platform/bootstrap` | virtual key alias `agent-hello` (budget 0.50) | **Blocks `make up`**: `platform_secrets --onboard` stops with `secrets:keys_without_manifest agent-hello`. |
| Secret `platform/redactor` | redactor client key `agent-hello` | The redactor still accepts that key. |
| Postgres (LiteLLM tables) | virtual key row `agent-hello` | Harmless without the key material, but still a valid key until deleted. |
| ConfigMap `ops/ops-agent-observe` | The `agent-hello.agent.observe` entry | Dropped by the next server-side apply (the field manager owns it). |

## Proposed one-time steps, in this order (each is a cluster write; run only after approval)

1. **Before `make up`:** remove the two Secret entries with `python3 -B -m agent_platform.platform_secrets --kubectl <kubectl> --retire-agent hello` (PYTHONPATH `platform/core/src:.`, kubeconfig of the live cluster). It drops the alias from `bootstrap.virtual_keys` and the redactor clients, rewrites only those two Secrets, rotates nothing else, prints alias names only, and a second run changes nothing. It refuses a name that still has a manifest.
2. `kubectl delete namespace agent-hello` (removes the pod, its Secret and its policies).
3. `kubectl -n platform delete networkpolicy agent-hello-to-gateway agent-hello-to-redactor`.
4. `make up` (the redactor restarts because its client keys changed).
5. Delete the LiteLLM key `agent-hello` through the gateway (`/key/delete`, master key from the owner shell), or leave it: no pod or Secret holds its value after step 2.
6. `make attack`: the suite now checks only `agent-financial`, and shows nothing left in `agent-hello`.

Rollback: the last Postgres snapshot (`make down`) covers the database. The deleted objects are generated and can be re-created from git history with `make onboard`.
