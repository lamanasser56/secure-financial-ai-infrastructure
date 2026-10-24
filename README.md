# Agent Runtime Platform

**Infrastructure · Security · Operations**

A Kubernetes-native platform for deploying, isolating, governing and observing AI agents.

This educational portfolio explores the boundaries between agent code, shared AI services, data access and operational authority. The Financial Agent is an example workload demonstrating controlled access to synthetic expense data. The Security & Operations Agent demonstrates bounded operational automation with application-level owner approvals. The Platform Guide searches a bundled documentation index.

## Implementation and evidence

The current implementation lives under `platform/`. Kubernetes manifests define namespace isolation, resource quotas, restricted workloads, scoped RBAC and bounded Ops admission. The gateway uses LiteLLM. The current redactor uses Google Sensitive Data Protection with deterministic client masking; references to Presidio in earlier phase material describe historical interfaces and experiments.

Financial requests pass through sign-in/session validation, tool selection, read-only data access, redaction and model dispatch, then answer validation and a per-turn trace. Some turns request tool data after the first model call. PostgreSQL policies filter rows by transaction identity context. These controls require the identity-setting application to be trusted.

The independent offline assessment demonstrated output-validation and Ops verification defects. The RC source preparation adds regression-tested corrections, including fail-closed handling of malformed responses. Its results do not establish live GKE enforcement or signed-image equivalence. Historical evidence remains unchanged; see [RC1 scope and limitations](docs/releases/rc1.md).

## Security limits and release status

RC1 is a proposed source candidate, not a published or deployable security certification. The historical runtime had the following HIGH boundaries; the proposed [v2 trusted-boundary source](docs/releases/rc1-boundary-migration.md) addresses them through separate services and identities. They are not fixed in the preserved historical images or live verified:

- Historical direct gateway access bypassed client redaction; the proposed trusted frontend redacts accepted messages and keeps upstream keys private.
- Historical workers held shared DB credentials and could choose RLS context; proposed workers receive only request capabilities and per-workload broker credentials.
- Historical Ops held direct patch authority; proposed Ops is read-only and delegates to an independent approval-verifying executor.
- Shared-service fairness, durable quotas, audit authenticity, disaster recovery and target-environment isolation still need independent runtime validation.

Focused local protocol and disposable-PostgreSQL tests qualify parts of the new boundaries; qualified artifacts, coordinated migration and live enforcement checks are still required. The original forty-case live assessment remains pending isolated-environment safety and authorization gates. Use synthetic data only. Do not treat historical cloud lifecycle commands as an isolated local demo.

## Repository map

| Path | Purpose |
| --- | --- |
| `platform/core/` | Platform services, Ops implementation, manifests, database SQL and tests |
| `platform/agents/financial/` | Example Financial Agent, authentication, read-only tools and output checks |
| `platform/agents/platform-guide/` | Example documentation-search agent |
| `platform/clouds/gke/` | GKE configuration and historical lifecycle tooling; not automatic deployment authority |
| `runtime/`, `contracts/`, `demo/`, `evaluation/` | Shared runtime and qualified historical inputs; preserve their integrity contracts |
| `docs/` | Architecture, security reviews, operations notes and historical evidence |

The [documentation index](docs/README.md) and [repository map](docs/REPO-MAP.md) provide more detail. Older names, release records and historical claims are retained for traceability; they are not a current verification verdict.

## Local validation

Use Python 3.12 and separately installed hash-locked dependencies. Financial tests use synthetic model/redactor fixtures; database-backed cases need a fresh disposable PostgreSQL instance and must report skips explicitly.

```bash
PYTHONPATH=platform/core/src:platform/agents/financial:platform/core/tests:. \
  python3 -B -m unittest discover -s platform/agents/financial/tests -p 'test_*.py'
PYTHONPATH=platform/core/src:platform/core/tests:. \
  python3 -B -m unittest discover -s platform/core/tests -p 'test_ops*py'
```

Read each test's prerequisites before broader validation. Do not run deployment, cloud, attack or teardown targets against existing resources as part of local validation.

## Artifact integrity and attribution

Existing image references, digests, signatures and attestations are historical release subjects. Source remediation requires separately reviewed new artifacts and qualification before deployment. A signed image does not authenticate executable ConfigMaps or database state. No historical pin or signature is updated by this source preparation.

This project continues infrastructure and runtime work adapted from the author's contribution to the private MASAR team project. It makes no ownership claim over third-party software or teammates' product implementations. Do not publish credentials, private assessment evidence or real financial records.
