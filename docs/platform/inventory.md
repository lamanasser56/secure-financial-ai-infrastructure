# Current source component inventory

This is a source ownership inventory, not a live cloud snapshot. Selected release facts, observed running digests and current checks identify a deployment. The earlier 15 October inventory is preserved in Git history; its old roles, UI routes and teardown checklist are not current instructions.

| Component | Current role | Source owner |
| --- | --- | --- |
| Console/app | Selected-release API, UI and owner approval signer | `agent_platform.app`, `console`, release facts/verification modules |
| Financial frontdoor/broker | Sign-in, user entry/routing, capability issuance and registered scoped reads | `finance_agent.frontdoor`, `data_broker`, `agent_platform.data_capability` |
| Financial workers | Separate user-bound processes with no DB/session/signing credentials | `finance_agent.worker`, `agent`, tools and onboarding render |
| Guide | Current bundled documentation search and bounded agent turn | `platform/agents/platform-guide/src` and its explicit corpus manifest |
| Mandatory model boundary | Accepted-message masking and caller-to-private-key dispatch | `agent_platform.gateway_boundary` |
| Redactor | Existing supported pattern/SDP contract | `programs/redactor_server.py`, `redaction.py`, runtime redaction modules |
| Private gateway/provider path | Scoped upstream model alias/keys and provider transport | Gateway/bootstrap/provider configuration |
| Postgres | Trusted frontdoor/broker roles, forced RLS and platform gateway store | `platform/core/database`, bootstrap |
| Ops observer | Read-only diagnosis, current posture and proposals | `agent_platform.ops.agent`, posture/registry |
| Approval executor | Independent signature/binding/replay checks and bounded mutation | `agent_platform.ops.executor`, approval, RBAC/admission |
| Shared UI assets | Blueprint stylesheet, generic drawer and self-hosted fonts | `platform/core/ui/shared-assets.json` and canonical files |
| Release | Selected deployment digests and typed staged apply | `release-rc1.lock.json`, cloud render/lifecycle/readiness |

`ops/authority.json` is the managed RBAC authority, including the executor's exact role reference and subject. Generated roles/bindings are outputs, not a parallel editable source. The executor's replay database uses the declared `ops-approval-replay` persistent claim; that store is not a general request audit or a backup/restore guarantee.

The supported screens are Console on 8080, trusted Financial on 8081 and Guide on 8082, all through approved local forwards. The previous demo UI and monolithic Financial composition must not be mistaken for those active services. [Repository map](../REPO-MAP.md) covers files; [architecture](../architecture.md) covers trust paths; [request events](request-trace.md) covers trace limits.

Engineering VMs are outside the workload deployment. Keep `secure-infra-worker`, `sfai-engineering` and their retained disks until an explicit deletion request. A historical empty-project teardown checklist does not override that retention or expand a disposable assessment's cleanup scope.
