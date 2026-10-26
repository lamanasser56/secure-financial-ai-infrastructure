# Current threat model

Scope: current boundary-v2 source, synthetic data and the declared private GKE workload deployment. The selected release lock and observed running digests identify a deployment. The [claims matrix](../agent-platform/claims-matrix.md) separates current controls/offline tests from historical and required new live evidence.

| Threat | Enforcing boundary | Current scope |
| --- | --- | --- |
| Hostile worker skips its masking client | Mandatory `gateway-boundary`, private upstream credentials and network policy | Accepted model messages pass trusted redaction before dispatch. Public worker keys do not authenticate directly to the private LiteLLM path. Names/passports remain outside masking coverage. |
| Worker chooses another user's SQL identity | Trusted frontdoor routing, signed active user/agent capabilities and data broker | Worker has no DB/session/signing credential or direct Postgres path. Broker sets the user under forced RLS; registered tools are read-only. |
| Forged or stolen browser session | Trusted frontdoor, signed expiring cookie, exact Host/Origin and CSRF | User identity comes from the verified session. Revocation/throttle state has the process scope described in limitations. |
| Prompt/tool injection | Closed worker decision/tool schemas and trusted external boundaries | Model text cannot grant database or Kubernetes authority. Pattern filters and selected-claim checks are additional, incomplete measures. |
| Ops observer or model text mutates a workload | Independent executor, signed bound owner approval, RBAC and admission | Observer proposes; executor alone holds declared patch rights. Read-only targets cannot be changed. Template changes outside allowed restart/scale bounds are refused. |
| Unexpected RBAC subject or binding | One declared authority inventory and current rendered-RBAC tests | Posture compares exact role references/subjects. A missing/unreadable/stale/incomplete scan cannot become a current zero-findings verdict. |
| Workload reaches public/provider/metadata endpoints directly | Private workload networking, default deny, explicit allow paths and token hardening | Network tests cover their declared paths/protocols. DNS exfiltration is not implied to be solved. Engineering VM networking is outside this claim. |
| Unapproved image or source confusion | Digest selection, scan policy, signature/KMS checks, source provenance and release process | Verify each evidence type for the exact subject. Historical passes do not establish current-source behaviour. |
| Content leaks through a trace or log | Bounded event schemas and content-free fields | Worker metadata is not an independent complete audit. Credential scans alone do not prove that every log contains no personal data. |
| Shared capacity or recovery failure | Per-service bounds, resource declarations and operator recovery procedures | No universal availability, backup/restore or durable quota guarantee follows. |

The trusted computing base includes the authentication frontdoor, capability issuer/broker, mandatory model boundary/redactor/private provider path, approval signer/executor, database, Kubernetes/cloud enforcement and release toolchain. Onboarded workers and all user/model text are outside that authority boundary.

Residual limits and their consequences are in [known limitations](known-limitations.md). Dated reviews and assessment reports remain evidence for their recorded source, images, settings and tested cases; they are not a substitute for the final exact-image assessment.
