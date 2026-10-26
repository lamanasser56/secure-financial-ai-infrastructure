# Secure AI Agent Platform

A private GKE agent platform with a Console, a Financial Agent UI and a documentation Guide. Untrusted workers use trusted model/data boundaries; a separate executor performs approved, bounded operational changes. The repository includes the current implementation, offline qualification, image/release tooling and historical assessment records. Examples and tests use synthetic data.

## Current platform

- **Model gateway:** mandatory request boundary → redactor → private LiteLLM/provider path. Public worker credentials do not bypass mandatory masking. Supported identifier patterns are masked; **person names and passport numbers are not masked**.
- **Data broker:** the trusted Financial frontdoor owns sign-in and routes each user to a bound worker. Active signed capabilities and forced row-level security bind registered read-only tools to that user. Workers hold no database/session/signing credentials.
- **Approval executor:** Ops observes and proposes. The trusted app signs owner approval; the independent executor, exact RBAC inventory and admission policy bound the permitted mutation.
- **Console:** Map, partial agent passports, read-only Onboard review, Ops scan/actions and release-bound Break it results. A worker trace is reported metadata, not an independent complete audit.
- **Financial and Guide:** separate local screens using one blueprint asset source. Financial's forms, errors and drawers support English/Arabic. Guide knowledge comes from an explicit current documentation corpus bundled into its image.

[Architecture](docs/architecture.md), [onboarding contract](docs/agent-onboarding-contract.md), [known limitations](docs/security/known-limitations.md) and the [current evidence matrix](docs/agent-platform/claims-matrix.md) define the scope. Current source, the selected deployed release and a historical live pass are different things.

## View and qualify

The selected `platform/clouds/gke/release-rc1.lock.json` is the deployment image authority. Source-generator defaults and old image tags are not release evidence. `make up` renders typed selected-release values and applies the reviewed stages. `make demo-check` requires actual ready resources and exact image proofs; a down cluster is not ready.

| Command | Local screen |
| --- | --- |
| `make port-forward` | Console at `http://127.0.0.1:8080/` |
| `make agent-forward A=financial` | Trusted Financial UI at `http://127.0.0.1:8081/` |
| `make agent-forward A=platform-guide` | Guide at `http://127.0.0.1:8082/` |

See [how to view](docs/HOW-TO-VIEW.md) and the [recording runbook](docs/operations/demo-runbook.md). Deployment/live commands require the approved operator environment. Code and offline tests belong on the engineering worker; the all-image build runs on `secure-infra-worker`. Persistent VMs/disks are retained until an explicit owner deletion request.

The final release sequence is source freeze **S** → first-party builds from **S** → cryptographic subject/source verification → lock/evidence-only promotion **R** → deploy the same digests → readiness → the approved exact-image disposable assessment → reset/onboarding/attack checks → full screen walkthrough. Historical evidence cannot replace this sequence for new source.

## Engineering checks

Use the pinned Python 3.12 dependency locks and the repository's declared tools on a Linux worker. `scripts/check.sh` checks contracts/reference suites; the CI `agents` job additionally runs current runtime/core tests, real API-server policy checks, real Postgres, Guide and browser suites. Read their actual required dependencies and commands in `.github/workflows/ci.yml`. A subset or skipped prerequisite must not be called full readiness.

The image workflow scans all severities and applies the unchanged HIGH/CRITICAL-or-any-KEV gate, with only the existing reviewed filelock exception. Before source freeze, refresh pinned bases and remediate every applicable finding with an available fix; record allowed no-fix findings per image. See [release policy](docs/security/container-vulnerability-release-policy.md).

## Repository and history

The [repository map](docs/REPO-MAP.md) identifies component ownership. Runtime/contracts/evaluation code must be judged by its current consumers; a prior phase name or old qualification hash is not a reason to postpone cleanup until teardown. Historical evidence, ADRs and archived inputs are outside the Guide's current corpus. The old loopback demo on port 8765 is a synthetic reference, not the current platform UI.

Do not commit credentials, private operator state, cloud project identities or real user content. The current APIs and recorded outputs have bounded disclosure scopes; keep private cloud command output out of the recording.

The Python runtime, contracts, infrastructure manifests and qualification fixtures were adapted from my MASAR AI Infrastructure contribution. MASAR was a team project; its product frontend and backend remain with their original contributors. Public third-party projects retain their upstream names and licenses. This repository makes no claim of ownership of those upstream projects and is released under the [MIT License](LICENSE).
