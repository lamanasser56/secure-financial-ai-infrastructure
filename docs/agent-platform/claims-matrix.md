# Current controls and evidence matrix

This is the current source-level control inventory. **Implemented**, **tested offline**, **observed in a deployment** and **qualified by a specific live assessment** are distinct states. A UI observation or inference never promotes the whole platform to VERIFIED. Historical reports retain their original source/image scope.

| Control | Current authority | Current verification and limit |
| --- | --- | --- |
| Mandatory model masking | `agent_platform.gateway_boundary`, redactor contract and private upstream keys | Trusted-boundary tests exercise raw/malicious callers and redaction failure. The exact selected images still need the release's live qualification. Person names/passports are not masked. |
| User-bound reads | `finance_agent.frontdoor`, `data_broker`, `worker`, `agent_platform.data_capability` and forced RLS | Current HTTP/capability tests and real Postgres tests exercise caller/user binding, no worker DB credentials, role permissions and row scope. Worker traces are not independent broker proof. |
| Bounded mutations | Approval signer, `ops.executor`, authority inventory and admission | Signature/binding/replay tests and real API-server RBAC/admission tests cover exact current targets and denials. Only an actual verified rollout establishes the requested action's result. |
| Exact RBAC posture | `ops/authority.json`, generated RBAC and `ops.posture` | Tested against current rendered RBAC, including executor roleRef/subject and refusal of extra subjects. Incomplete/stale/unreadable scans show no current clean verdict. |
| Namespace/workload/network controls | Onboarding renderer, Kubernetes policy and GKE declarations | Current render and API-server tests; network qualification must exercise the deployed paths with healthy controls. TCP tests do not establish all DNS/UDP behaviour. |
| Image admission and supply chain | Selected release lock, image gate, cosign/KMS evidence and Binary Authorization | Digest/signature/attestation readiness is separate from source provenance and actual admission tests. Verify the exact subject and expected source, not a tag or workflow certificate alone. |
| Financial/Guide output checks | Registered tools and each current agent's admission code | Financial tests exercise its current admission rules. Guide code returns only selected indexed excerpts and refuses model-authored prose; source selection is not a semantic or deployment proof. |
| Request events | Closed event fields and bounded local metadata | Current schema/content tests. No complete or durable audit-before-mutation promise. |
| Console and recording commands | Selected release facts, current API projections, browser/CLI tests | Browser tests use current components with explicit synthetic fixtures. A down cluster, missing prerequisite or NOT_EXERCISED attack is not a live PASS. |

## Live evidence rule

The final release procedure freezes source **S**, builds its first-party images, verifies signatures/attestations and source binding, promotes only lock/evidence metadata in **R**, and deploys those same digests. Readiness, the disposable-project assessment and the final live checks must record their exact image subjects and scope. They must not borrow a previous report's pass count.

The current attack suite's required attacks and positive controls are declared by `CASES` in `platform/core/src/agent_platform/attack_results.py`; the executable owner registry must match it. Use this authority rather than historical case names or counts. A failed case dominates NOT_EXERCISED, and missing exercise is not success. Mounted results must be bound to the selected release and runner source.

The deployment manifests changed after the older assessment, including node-local DNS egress and staged apply from PR #142. Those changes match that assessment bundle's corrections; that correspondence does not independently qualify later code or images.

Historical evidence is under `docs/evidence/` and immutable Git revisions. Earlier snapshots of this matrix and the 19 October inventory remain available in Git history. They are excluded from the Guide's current corpus. See [limitations](../security/known-limitations.md) and [threat model](../security/threat-model.md).
