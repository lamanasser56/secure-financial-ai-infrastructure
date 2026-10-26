# Put an agent on the current platform

Start from a current working manifest in `platform/agents/`. The platform validates a closed shape and generates security-relevant workload objects; do not copy an old rendered manifest or request additional egress to make a failing worker work.

## Review and render

```bash
make onboard-check F=platform/agents/<name>/agent.yaml
make onboard A=<name>
```

`onboard-check` reviews a file without writing generated objects. `onboard` validates a declared agent and regenerates the platform-owned objects. A rejection exits nonzero and writes no generated objects. The intentional rejected example is:

```bash
make onboard-check F=docs/examples/rejected-agent/agent.yaml
```

Its nonzero exit is expected. The Console's Onboard screen is a read-only review; its manifest table is a summary, and it does not create an agent or grant permissions. Refresh re-reads facts.

The [contract](agent-onboarding-contract.md) lists the current fields. Image names are logical aliases. The deployment authority is the selected `platform/clouds/gke/release-rc1.lock.json`; `images.json` still supplies source-generator defaults and is not proof that an image is current, deployed or qualified. Release rendering must select the lock's digests rather than treating defaults as a second release authority.

## Implement the worker

Provide the declared entrypoint, listening port and health endpoint. Use the registered model alias and bounded decision/tool schema. Treat all user/model text and fetched content as untrusted data. Client masking is useful, but the mandatory model boundary independently masks accepted messages and keeps its private upstream key outside the worker.

Do not put database credentials, session keys, approval signing keys or provider credentials into a worker. The Financial example uses a trusted user frontdoor and broker with active, signed user/agent capabilities. A new data-bearing agent needs its own reviewed broker contract; `data` is not permission to connect directly to Postgres or set any user's RLS identity.

Ops observes onboarded workers read-only. An incident does not create patch permission. The executor's mutable target registry, exact RBAC authority and admission rules are separate platform-owned controls.

## Test and release

Run `make test` on a fresh GitHub-hosted runner or an engineering VM for the same current runtime, API-server policy, real Postgres, Guide and browser suites. The VM is only an interactive work surface. Synthetic transport fixtures must be identified as such; they are not live provider or deployment evidence. A skipped prerequisite is not a complete readiness result.

Merge only after the required checks pass. Build/scan/sign/attest the intended source, verify exact subjects and source binding, promote the release lock, then deploy with the staged `make up` path. No post-render repair or runtime source overlay should substitute for a supported image entrypoint. Current render/authority invariants must pass before any final cluster use.

## Reach the screens

| Command | Local screen |
| --- | --- |
| `make port-forward` | Console: `http://127.0.0.1:8080/` |
| `make agent-forward A=financial` | Trusted Financial UI: `http://127.0.0.1:8081/` |
| `make agent-forward A=platform-guide` | Guide: `http://127.0.0.1:8082/` |

Use the exact supported local address and keep each forward open. Port-forwarding is operator access; it does not turn a worker into the trusted Financial login service. Deployment/forwarding requires the approved owner environment, while offline tests need no deployment-cluster access.

See the [architecture](architecture.md), [viewing guide](HOW-TO-VIEW.md), [runbook](operations/demo-runbook.md) and [limitations](security/known-limitations.md).
