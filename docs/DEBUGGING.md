# Debug current boundaries

During code/test themes, reproduce failures with current components and offline fixtures on the worker. Do not repair a live Pod or substitute security code to make a check pass. Final cluster reads/mutations use the selected release and the approved deployment/verification scope.

## Find the authority

| Symptom | Start with |
| --- | --- |
| Sign-in, CSRF or session failure | Trusted `finance_agent.server.Handler` composed by `finance_agent.frontdoor`, `Sessions` and `LoginThrottle`; workers do not own login |
| `worker_unavailable` | Trusted frontdoor route/capability/transport and the bound worker; the code must not relabel its own rate limit as worker failure |
| `rate_limited` / `token_budget_exhausted` | The current process's limits and reset scope; no durable multi-process quota inference |
| Masking/model failure | Worker client report and the mandatory `GatewayBoundary`'s independent refusal/event; a failed later call does not mean no earlier model call happened |
| Missing rows or tool refusal | Active user/agent capability, broker registry/arguments, trusted broker role and forced RLS; do not put a DB credential into the worker |
| Untrusted or unsupported answer | Actual worker admission checks and returned tool excerpts/results; do not treat a figure check as semantic proof |
| Posture finding or missing verdict | Current authority inventory, rendered RBAC, actual scan source/start/end/completeness; an API error or partial scan is not zero findings |
| Missing workload observation | Every selected worker/core target and its own observation age, not an obsolete single-worker deployment name |
| Approval refused | Current proposal/binding/expiry, owner credential, independent executor and fresh resource version/evidence; model text grants no authority |
| Lost execution response | Unknown outcome: inspect current incident/workload state before another attempt; never automatically replay it |
| Image/admission/readiness failure | Selected lock subject, desired/running digest, owner chain, cryptographic proofs and actual ready resources; no text-transform image repair |
| Guide cites stale content | Explicit current corpus and built index source/file hashes; do not fall back to historical ADRs or assessment records |

## Trace scope

The worker trace is reported metadata. The mandatory gateway creates its own ID and overwrites caller metadata; trusted broker references also have their own source. There is no verified universal request-ID join. Follow the component's actual bounded fields and do not fabricate a complete cross-boundary trace from a worker response. See [request events](platform/request-trace.md).

Use current API/CLI summaries first. Private operator logs may contain cloud identities or image paths; they are not recording-safe merely because a bounded trace is content-free. Never print credentials or private project identifiers while debugging.

## Readiness and controlled recovery

`make demo-check` requires the selected resources to be up, ready and matched to verified subjects. `make demo-reset` returns to the declared demo state and fails if a required step is incomplete. The intentional rejected onboarding example exits nonzero. `make attack` is a live owner operation reserved for the final approved scope; an unavailable control is NOT_EXERCISED, not PASS.

Fault demonstrations and operational recovery must target the declared workload and signed approval flow. Correct the source/manifest/image, run its tests/CI and promote the selected release; do not keep an ad hoc live edit as the fix. Persistent engineering workers are not teardown targets.
