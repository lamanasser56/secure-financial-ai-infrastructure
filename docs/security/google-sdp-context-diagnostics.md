# Context-001 fail-closed diagnosis and proposed diagnostic run

**Offline preparation; no execution authority.** Presidio remains authoritative,
its remediation remains paused, and Google SDP remains unwired from the agents.
This assessment does not authorize a release, provider call, cloud mutation,
campaign rerun or authority change.

## Retained observation and its limits

The completed `context-pattern-v1` execution used source
`7e8a855842e91ed29d437f571f80c558ab68584c` and stopped at `context-001`.
Its sanitized result records one required `FAIL_CLOSED`, two content SDK invocation
attempts, zero retries and 85 unexecuted cases. The result hash is
`15d5c8db3ddae3f4a0a75a36f5dde8af6559f38da679535ba0a384e8716c40cf`.
The private execution report, minimized result, workload summary and cleanup
verification remain retained separately; no raw response or exception was retained.

The fixed [adapter sequence](../../runtime/phase3/google_sdp_adapter.py) dispatches
inspection, validates its result and only then attempts de-identification. Thus
inspection returned through its local guards. The second invocation counter does
not establish that de-identification returned successfully, that Google received
both operations, or that any particular post-response guard ran.
The original cause is **UNKNOWN**. The zero `tp`/`fp`/`fn` failure placeholders are
not detection scores. No conclusion that detection failed follows from this result.

The signed image and its exact source remain historical subjects. It does not
contain the new diagnostic implementation. Its manifest is
`sha256:c5035f6270be3e9afa69a9ad939b7c0b76851face8e770a08de30556952dd962`;
its different configuration identity is
`sha256:8c0a7f6042abeb3f811a1f01aa0440a0bb0a67399ef2ae7ab9e346855126b62d`.
The [retained qualification record](../../evaluation/google-sdp-context/qualification.json)
cannot qualify changed adapter, harness or schema bytes. Future image qualification
must bind the final source and every new image input; old scan/SBOM evidence must
not be relabelled as evidence for that image.

## Failure paths after inspection

| Stage | Fail-closed condition | What retained evidence establishes |
| --- | --- | --- |
| Second invocation | SDK request serialization, authentication, RPC status or SDK deadline failure, including rejection of capture-group/transformation configuration | The invocation was attempted; status and server receipt are unknown. |
| Deadline guards | Per-RPC elapsed time exceeds its supplied timeout; combined monotonic deadline expires before or after response validation | No retained stage or clock measurement identifies a particular guard. |
| Response structure | Missing item, wrong `data_item` oneof, non-string/blank/oversized output, missing or malformed overview/summary | Response shape was not retained. |
| Output preservation | Output differs from reconstruction using validated spans and the selected replacement | Successful substitution and preservation are unproven. |
| Residual-value rejection | A canonicalized sensitive fragment remains in output | Neither residual text nor a residual-rejection flag was retained. |
| Transformation completion | Unexpected type/transformation, failure/detail-bearing result, missing/extra counts, inconsistent transformed-byte statistics | Statistics were not retained; constructed SDK objects alone do not prove Google's values. |
| Neutral result | Category reconstruction, UTF-8 bound or final overall deadline fails | No neutral redacted result escaped the failure. |

### Confirmed compatibility defect and diagnostic gap

The historical output guard accepted only bare infoType replacements. Google's
[custom-dictionary REST example](https://docs.cloud.google.com/sensitive-data-protection/docs/creating-custom-infotypes-dictionary?hl=en)
uses the same `replaceWithInfoTypeConfig` and returns bracketed `[CUSTOM_ROOM_ID]`
tokens. The [transformation reference](https://docs.cloud.google.com/sensitive-data-protection/docs/transformations-reference?hl=en)
also describes a bare-token output. Rejecting every bracketed response therefore
contradicts a documented response form. This is a confirmed compatibility defect;
it is **not proof of the original cause**, because that response was not retained.

The bounded correction accepts only two complete, exact reconstructions: every
replacement bare, or every replacement bracketed. It rejects mixed forms, arbitrary
brackets, partial substitution and changes to surrounding text. After validation,
the adapter emits the existing bare or provider-neutral category result. Residual
checks, byte limits, transformation statistics and deadlines remain mandatory.
Neither undocumented output forms nor general response rewriting are accepted.

The historical boundary also deliberately reduced all exceptions to the same public
`redaction:provider_failure`. It contained raw provider data but prevented distinguishing
failure paths. RPC/deadline failures, capture-group behavior and statistics incompatibility
remain separate hypotheses about the original run unless supported by independent evidence.

The [overview contract](https://docs.cloud.google.com/sensitive-data-protection/docs/reference/rest/v2/TransformationOverview)
defines aggregate and per-summary transformed bytes, result counts, success/error
codes and potentially sensitive details. The output guard keeps consistency and
complete-success checks, and rejects detail-bearing results without copying those
details. SDK field presence, oneofs and enums are checked against the
[locked 3.40.0 types](https://raw.githubusercontent.com/googleapis/google-cloud-python/google-cloud-dlp-v3.40.0/packages/google-cloud-dlp/google/cloud/dlp_v2/types/dlp.py).

The [context policy](../../runtime/phase3/sdp_context_policy.py) supplies the same
fixed inspection configuration for both RPCs, with capture group `1` for its custom
regexes. Its [policy matrix](google-sdp-context-policy.md) defines finite supported
labels and unsupported boundaries. No diagnostic change selects a broader detector,
unrestricted fuzzy matching or a new value policy.

## Sanitized diagnostics and offline verification

Diagnostics use finite allowlists for failure category, stage and RPC status.
The public error stays `redaction:provider_failure`, without an exception cause or context.
No diagnostic contains input/output text, findings, spans, response bodies,
transformation details, exception messages, project identities or credentials.

| Diagnostic category | Bounded codes |
| --- | --- |
| Timeout | `RPC_TIMEOUT`, `OVERALL_TIMEOUT` |
| RPC | `RPC_STATUS`, `RPC_FAILURE`; only a recognized finite gRPC status is retained. |
| Response | `MALFORMED_RESPONSE`, `INCOMPLETE_TRANSFORMATION`, `OUTPUT_MISMATCH`, `RESIDUAL_VALUE`, `OUTPUT_LIMIT` |
| Admission/control | `INVALID_INPUT`, `CONFIGURATION_REJECTED`, `BUSY`, `BUDGET_EXHAUSTED` |
| Unclassified | `UNKNOWN`; does not imply a specific provider or detector failure. |

Allowed stages are `startup`, `input`, `budget`, `inspect`, `inspect_response`,
`deidentify`, `output`, `normalize` and `sequence`. Unknown exceptions cannot supply
arbitrary stage/status strings or their messages. Local timeout checks and classified
SDK exceptions do not relax the three/eight-second deadlines or permit retries.

The [result schema](../../evaluation/google-sdp-context/result.schema.json) bounds
any emitted diagnostic and retains compatibility with historical minimized results.
A failed-closed diagnostic is explanatory metadata, never a successful redaction or
accuracy score. Counts continue to mean attempted invocations, not billed operations.

Verification uses representative `google-cloud-dlp==3.40.0` response and exception
objects offline on `secure-infra-worker`, with no SDK client construction or network
dispatch. Request protobufs validate configuration shape; response protobufs validate
presence, oneofs and enums. Their contents are chosen from documented API contracts,
not adjusted merely to satisfy the adapter. Tests cover valid and malformed responses,
timeouts, sanitized RPC statuses, incomplete transformations, residual values and
the original fixed error contract. Real SDK objects are transport fixtures, not Google
detection evidence. Any proven guard correction requires a cited contract and a
regression reproducing the previously rejected contract-valid response.

The provider-neutral redactor boundary, per-call limits, operation accounting,
fail-closed output handling and lack of production wiring remain intact. Raw
conversation, response and exception content stays out of logs and reports.

## Proposed first-case-only diagnostic bundle

**Preparation proposal only; a separately approved, fully frozen bundle is required.**
The earlier 172-attempt approval was consumed by its completed execution and does
not authorize a new two-attempt run. Do not rerun the 86-case campaign to obtain
diagnostics.

| Boundary | Proposed limit or exact existing contract |
| --- | --- |
| Input | Only committed `context-001` from the unchanged frozen corpus; no supplied text, arbitrary file or selectable case. |
| Policy/corpus | `context-pattern-v1`; preserve the committed policy and all 86 cases byte-for-byte, but dispatch only the first case. |
| SDK attempts | At most one inspect and one deidentify: **two content attempts total**, including failures; zero SDP metadata SDK calls. |
| Retries | Zero application, content-SDK and Job retries; one Job/Pod, no automatic restart/recreation. |
| Text/deadlines | Input/output at most 4,096 UTF-8 bytes; RPC three seconds; combined monotonic eight seconds. Proposed Job deadline 120 seconds. |
| Location | Only `us-east1`, `dlp.us-east1.rep.googleapis.com`, and `projects/PROJECT_ID/locations/us-east1`; no fallback, request-selected location or alternate project. |
| Identity | Existing runtime GSA and namespace/KSA `google-sdp-evaluation` / `google-sdp-evaluation`; no new keys, permissions or identities. |
| Kubernetes controls | Existing restricted PSA, nonroot UID/GID 65532, read-only root, no escalation, dropped capabilities, RuntimeDefault seccomp, bounded resources and one-Job/Pod quota. |
| Output | Fixed case/policy/source identity, neutral outcome, finite diagnostic values and operation counts only; no raw text, findings, spans or provider detail. |
| Decision | Diagnose the first failure only. A pass permits review of the next qualification proposal; it does not authorize that campaign or replacement. |

Before the single execution checkpoint, preparation must resolve the following:

1. Freeze and locally qualify the final diagnostic source. Bind the unchanged
   policy/corpus hashes, fixed `--diagnostic-first-case` selector, both the existing
   synthetic acknowledgement and its distinct diagnostic acknowledgement,
   minimized result schema and exact operation budget in regression tests.
2. Produce new deterministic image archives/configuration evidence, fresh SBOM,
   scan and unchanged zero-exception vulnerability policy on the worker. The existing
   signed image cannot be reused to claim execution of new diagnostics.
3. Freeze one reviewed manual release, its exact inputs and source-SHA-only WIF
   proposal. Preserve every other trust condition, attribute mapping, IAM binding,
   registry rule and GitHub protection. Resolve and verify the actual new manifest
   signature before deployment; configuration digest is not a manifest digest.
4. Prepare a reviewed first-case-only rendered Job and offline validator. The current
   [context renderer](../../scripts/render-sdp-context-job.sh) sets `--live` for the
   whole campaign and must not be used unchanged for this diagnostic run. A selector
   added to the harness must be fixed and bounded, with no general corpus override.
5. Bind exact private project, names, source/configuration hashes and proposed image
   subject outside Git. Recheck authenticated inventory and review complete saved
   creation and cleanup plans before any mutation. Stop on drift or unrelated actions.
   No new API, billing arrangement, role or alternate resource is proposed.

The execution checkpoint is **not ready** until these exact subjects and reviewed
rendering/plan differences are available. Do not approve or execute an unspecified
future image, source commit, acknowledgement or saved plan.

### Resources and execution order

Reuse the existing [enumerated identity and infrastructure boundary](google-sdp-context-execution-bundle.md):
15 retained identity-root resources, the disabled node GSA, both private state
prefixes and the separately retained state bucket. Create only these eight previously
removed temporary resources and enable the retained node GSA for their lifetime:

| Temporary resource | Existing name/location | Cleanup |
| --- | --- | --- |
| VPC | `google-sdp-evaluation`, global | Delete. |
| Subnet | `google-sdp-evaluation`, `us-east1` | Delete with owned ranges. |
| NAT address | `google-sdp-evaluation-nat`, `us-east1` | Release. |
| Router | `google-sdp-evaluation`, `us-east1` | Delete. |
| Router NAT | `google-sdp-evaluation`, `us-east1` | Delete. |
| Node system-role binding | Existing node GSA, project `roles/container.defaultNodeServiceAccount` | Remove temporary binding. |
| Cluster | `google-sdp-evaluation`, `us-east1-b` | Delete, including partial creation. |
| Managed node pool | `evaluation`, `us-east1-b` | Delete with its VMs/disks/MIGs. |

This retains the prior 24 Terraform-resource inventory plus its separate state
bucket. Keep locked Terraform/Google-provider versions, the approved GKE version,
single private `e2-standard-2`/20 GiB node, removed default pool and all cluster
security controls. Do not substitute a new version if availability fails.

After approval and reviewed saved-plan apply, native admission/schema and identity
checks precede an independently correlated zero-SDP-call network preflight.
Metadata verification reads the runtime account email only, never a token. Require
regional TLS/HTTP2 allow evidence plus genuine unrelated resolved/direct HTTPS and
alternate-DNS denies with matching native datapath verdicts. A timeout alone is not
enforcement proof. Delete the probe Job/Pod/ConfigMap, verify quota availability,
create the diagnostic Job suspended and unsuspend it once. A failed gate starts
cleanup immediately; it never triggers another release, Job or diagnostic call.

Native FQDN enforcement remains DNS-derived IP/port control, with shared-IP,
Layer-7 and DNS-query limitations. TLS/application endpoint pinning is mandatory.
Project-wide workload-pool reuse is not cluster-specific identity isolation.

### Cost, cleanup and retention

Retain the **USD 5 incremental operator stop rule**, which is not a guaranteed billing
cap. Recheck regional prices before execution; include node/control-plane/disk/NAT/IP,
transient default-pool, registry, state, logging, transfer and the two content attempts.
Actual receipts and billed operations cannot be inferred from client counters.

The two-hour temporary-infrastructure clock starts at the first creation apply,
including partial resources. Begin cleanup by minute 90 and immediately after any
failure, targeting verified deletion by two hours. No automated cluster expiry
exists; the owner must resume or take over cleanup if the session disconnects.
Job completion TTL is not cluster cleanup.

Retain minimized evidence before workload deletion and workflow-artifact expiry.
Remove only owned workloads/namespace/scoped logging and the eight temporary
resources using reviewed cleanup plans. Verify cluster/pools/VMs/disks/MIGs,
VPC/subnet/router/NAT/address/firewalls/routes absent, temporary node role removed
and node GSA disabled. Remove new private credentials/plans/backend caches after
retaining sanitized summaries; preserve platform-managed authentication and unrelated
workspaces. Keep the private state, identities/WIF/approved bindings/shared APIs,
inactive node registry-reader grant, immutable images/signatures and sanitized
90-day evidence. Retained storage may continue costing. MASAR and the standing
worker/offline UI are outside cleanup.

## Gates remaining after a diagnostic result

Resolving `context-001` alone cannot qualify replacement. The remaining 85 campaign
cases, finite Arabic/English variants, unsupported boundaries and the broader
eight-class qualification remain unmeasured. Span precision/recall, preservation,
complete/truncated responses, statistics, obfuscation/Unicode/OCR behavior, latency,
repeated-agent budgets, durable audit and detector drift still need review.

Raw-data processor/privacy/location review, independent review, live gateway/model,
scoped client credential, trusted identity/tenant/database integration and an explicit
provider-selection/retirement decision remain separate acceptance gates. Historical
state-read/history, missing IAM deltas, impersonation/signed-URL/worker credential and
transient bootstrap-node UNKNOWNs remain recorded. No Saudi-residency, production,
Presidio-replacement or full-CS6 claim follows from diagnostics. Zero source-scan
findings do not prove universal secret protection.
