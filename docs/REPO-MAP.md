# Repository ownership map

Current implementation, release metadata and historical evidence have different owners and purposes. A phase name or old qualification record is not a reason to keep dead release inputs or defer source cleanup until cloud teardown.

| Area | Owner and purpose |
| --- | --- |
| `platform/core/src/agent_platform` | Console/API, typed facts, onboarding, mandatory model boundary, capabilities, clients, events, bootstrap and Ops authorities |
| `platform/core/kubernetes` | Platform workload/policy declarations and generated agent objects; RBAC derives from the single authority inventory |
| `platform/core/database` | Database schema/role reconciliation and synthetic seed inputs; category codes/labels and CHECK generation belong to `agent_platform.financial_schema` |
| `platform/core/ui` | Console application and canonical shared CSS/drawer/fonts, with exact public routes in `shared-assets.json` |
| `platform/agents/financial` | Trusted Financial frontdoor/broker, untrusted user-bound worker, registered tools and private UI; supported roles must not be confused with the older monolithic test composition |
| `platform/agents/platform-guide` | Guide runtime, declared current docs corpus/index builder, private UI layout and tests; no finance database access |
| `platform/clouds/gke` | GKE render/lifecycle, readiness/reset, actual architecture attack runner and cloud/Terraform integration |
| `platform/clouds/gke/release-rc1.lock.json` | Selected deployment release authority, promoted with evidence after subject/source verification |
| `platform/clouds/gke/images.json` | Legacy source-generator defaults; not a second deployment/release qualification authority |
| `providers` | Declared provider profiles and the approved alias/routing configuration |
| `runtime`, `contracts` | Shared libraries/contracts and their reference consumers; actual imports and image COPY/ignore inputs determine release use |
| `evaluation`, `demo`, `infra`, `archive` | Reference/evaluation or historical material where applicable; do not infer current product behaviour or live qualification from an old directory/tag |
| `assessment_overlay` | Assessment tooling and preserved reports; qualification must target supported current images/configuration, not substituted security code |
| `scripts` | Validation, lint, dependency locks, source inventory and supply-chain/release tooling |
| `tests`, `platform/core/tests`, component tests | Current behavioural/contract/HTTP/browser/API-server/Postgres tests, plus explicitly identified reference fixtures |
| `.github/workflows` | Required CI, supply-chain qualification and first-party image production; tests and image gates are separate checks |
| `policy` | Unchanged vulnerability policy and exact reviewed exception records; this directory alone grants no promotion |
| `docs` | Current engineering references plus clearly scoped historical records; the Guide's current corpus is explicit rather than a recursive scan |
| `docs/evidence` | Immutable/sanitized evidence for recorded source, images, settings and times; not the current product's default data source |

The current flow is documented in [architecture](architecture.md), [request events](platform/request-trace.md), [onboarding](agent-onboarding-contract.md) and [Ops](console/operations.md). Exact executable entrypoints come from the current Makefile and image definitions, not a copied historical command list.

`make up` selects the release lock and typed staged render. Source defaults, rendered outputs, signed image subjects, source provenance and runtime observations must not be substituted for each other. Signature/certificate scope is described in the [claims matrix](agent-platform/claims-matrix.md).

Build/test workers are persistent engineering resources outside the GKE workload boundary. Retain `secure-infra-worker`, `sfai-engineering` and their disks until explicit owner deletion approval. The disposable assessment's complete cleanup does not expand to those resources; see [retention and teardown](agent-platform/teardown-plan.md).
