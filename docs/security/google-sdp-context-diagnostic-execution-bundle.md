# Proposed context-001 diagnostic execution bundle

**Reversible preparation; no new execution authority.** This is one fixed
synthetic SDP diagnostic, not another full campaign, live-agent/model experiment
or Presidio replacement decision. Presidio remains authoritative and its
remediation remains paused. The final private approval handoff binds the exact
source SHA, approved project/account identifiers and retained state bucket.
`PROJECT_ID`, `PROJECT_NUMBER` and `REPOSITORY_ID` below represent only those
previously reviewed identities, not selectable alternatives.

## Frozen diagnostic subject

| Input or limit | Exact prepared contract |
| --- | --- |
| Release profile | `context-001-diagnostic-v1` |
| Policy | `context-pattern-v1`; SHA256 `c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db` |
| Corpus | Unchanged 86-case artifact; SHA256 `0c07aa1e8b480e732cdcaa6e9f406661058220ad41de607af7124198e5e71eb9`; only its first case, `context-001`, executes. |
| Fresh local image subject | Configuration, matching archive hashes, image-input hashes, tools and fresh SBOM/scan/policy evidence in the [diagnostic qualification record](../../evaluation/google-sdp-context/diagnostic-qualification.json). |
| Intended registry image | `us-east1-docker.pkg.dev/PROJECT_ID/sdp-evaluation-images/google-sdp-context-diagnostic` |
| Registry manifest/signature | Not published during preparation; resolve and verify after the single separately approved release. The local configuration digest is not the registry manifest digest. |
| Harness arguments | Exactly `--live --diagnostic-first-case`; no case, text, file, corpus or full-campaign selector. |
| Synthetic acknowledgement | `PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK=I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY` |
| Diagnostic acknowledgement | `PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK=I_ACKNOWLEDGE_CONTEXT_001_ONLY_TWO_ATTEMPTS` |
| SDK budget | At most one inspect and one deidentify invocation attempt: **two content operations total**, including failed attempts; zero SDP metadata SDK calls. |
| Retries | Zero SDK/application/Job retries; one Job/Pod; no automatic recreation, restart or release rerun. |
| Text/deadlines | Input/output 4,096 UTF-8 bytes; RPC three seconds; combined monotonic eight seconds; harness diagnostic admission 30 seconds. |
| Job | Suspended `google-sdp-context-diagnostic`; active deadline **120 seconds**, one completion/parallelism, backoff zero, completion TTL 3,600 seconds. |
| Temporary infrastructure | Two hours from first creation apply, including partial resources; cleanup starts by minute 90 or immediately on any failing gate. |

Fresh local qualification binds the changed adapter, harness and result schema;
it cannot be replaced by the historical signed context image or its old scan.
The original [qualification record](../../evaluation/google-sdp-context/qualification.json)
and completed campaign evidence remain historical, unchanged subjects. Local
offline reference output and constructed SDK objects do not measure Google's
detection quality. This proposal selects no arbitrary input and grants no real-data
authorization.

## Confirmed defect and unresolved historical cause

The [offline diagnosis](google-sdp-context-diagnostics.md) confirmed that rejecting
every bracketed infoType replacement contradicted a documented API response form.
The candidate now accepts only complete exact bare or bracketed reconstructions;
partial/mixed substitutions and changes to nonsensitive text still fail closed.
All existing statistics, byte, residual and deadline guards remain mandatory.

The historical `context-001` cause remains **UNKNOWN**. Two attempted invocations
show that inspection returned through local guards and de-identification was
attempted; they do not show nonzero detections, a successful second RPC, Google
receipt, billing or which post-response guard failed. The new finite diagnostic
codes contain no raw text, findings, spans, response bodies, transformation details,
exception messages or credentials. A diagnostic failure is not an accuracy score.

## Exact resource inventory

Reuse the 15 identity-root resources, disabled node GSA and private state bucket
after fresh authenticated inventory. Create only the same eight previously removed
temporary cluster-root resources and temporarily enable that node GSA. This remains
**24 Terraform resources plus the separately retained state bucket**. Terraform
1.16.5 and locked Google provider 8.5.0, resource names, topology, security controls
and limits stay unchanged. No API enablement, billing change, bootstrap/import,
provider upgrade, new role or unrelated deletion is proposed.

| Resource type/address | Exact name | Location | Action and cleanup disposition |
| --- | --- | --- | --- |
| `google_project_service.artifact_registry` | `artifactregistry.googleapis.com` | Project | Reuse enabled contract; retain. |
| `google_project_service.sdp` | `dlp.googleapis.com` | Project | Reuse enabled contract; retain. |
| `google_project_service.iam_credentials` | `iamcredentials.googleapis.com` | Project | Reuse enabled contract; retain. |
| `google_project_service.sts` | `sts.googleapis.com` | Project | Reuse enabled contract; retain. |
| `google_artifact_registry_repository.evaluation` | `sdp-evaluation-images` | us-east1 | Reuse immutable repository; retain historical and new image/signature subjects. |
| `google_service_account.release` | `google-sdp-release` | Project | Reuse keyless release identity; retain. |
| `google_service_account.runtime` | `google-sdp-runtime` | Project | Reuse keyless content identity; retain. |
| `google_iam_workload_identity_pool.release` | `google-sdp-release` | global | Reuse; retain. |
| `google_iam_workload_identity_pool_provider.github` | `github-release` | global | Update only the exact source-SHA condition to the final approved commit; retain all other conditions/mapping. |
| `google_artifact_registry_repository_iam_member.release_writer` | Release GSA writer binding | us-east1 repository | Reuse; retain. |
| `google_artifact_registry_repository_iam_member.node_reader` | Node GSA reader binding | us-east1 repository | Reuse; retain inactive after node disablement. |
| `google_service_account_iam_member.github_release_impersonation` | Repository-ID federation binding | Release GSA | Reuse; retain. |
| `google_service_account_iam_member.gke_runtime_impersonation` | Namespace/KSA federation binding | Runtime GSA | Reuse; retain. |
| `google_project_iam_custom_role.sdp_content_use` | `sdpContentUse` | Project | Reuse only `serviceusage.services.use`; retain. |
| `google_project_iam_member.runtime_content_use` | Runtime custom-role binding | Project | Reuse; retain. |
| `google_compute_network.evaluation[0]` | `google-sdp-evaluation` | global | Create dedicated VPC; delete. |
| `google_compute_subnetwork.evaluation[0]` | `google-sdp-evaluation` | us-east1 | Create dedicated subnet/ranges; delete. |
| `google_compute_address.nat[0]` | `google-sdp-evaluation-nat` | us-east1 | Create one NAT IP; release. |
| `google_compute_router.evaluation[0]` | `google-sdp-evaluation` | us-east1 | Create; delete. |
| `google_compute_router_nat.evaluation[0]` | `google-sdp-evaluation` | us-east1 | Create new-subnet NAT only; delete. |
| `google_service_account.node` | `google-sdp-evaluation-node` | Project | Reuse disabled account, enable temporarily; disable after cleanup. |
| `google_project_iam_member.node[0]` | Node system-role binding | Project | Create temporarily; remove. |
| `google_container_cluster.evaluation[0]` | `google-sdp-evaluation` | us-east1-b | Create dedicated temporary cluster; delete, including partial creation. |
| `google_container_node_pool.evaluation[0]` | `evaluation` | us-east1-b | Create one steady-state node; delete with VMs/disks/MIGs. |
| Separate retained state bucket | Exact existing name in private approval handoff | us-east1 | Reuse both private current states/version/soft-delete/lifecycle controls; retain with continuing storage cost. |

## IAM and governance

| Principal | Exact role or custom permissions | Resource scope and purpose |
| --- | --- | --- |
| Existing authenticated owner/operator | Existing project Owner authorization; no additional grant | Native Cloud Shell and reviewed saved-plan administration; no least-privilege operator claim. |
| `serviceAccount:google-sdp-release@PROJECT_ID.iam.gserviceaccount.com` | `roles/artifactregistry.writer` | Evaluation repository only; publication. |
| `serviceAccount:google-sdp-evaluation-node@PROJECT_ID.iam.gserviceaccount.com` | `roles/artifactregistry.reader` | Same repository only; node image pull. |
| Same node GSA | `roles/container.defaultNodeServiceAccount` | Project; temporary minimum node-system contract, not content access. |
| `principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/google-sdp-release/attribute.repository_id/REPOSITORY_ID` | `roles/iam.workloadIdentityUser` | Release GSA only; provider additionally enforces exact GitHub claims. |
| `serviceAccount:PROJECT_ID.svc.id.goog[google-sdp-evaluation/google-sdp-evaluation]` | `roles/iam.workloadIdentityUser` | Runtime GSA only; project-pool identity reuse remains a limitation. |
| `serviceAccount:google-sdp-runtime@PROJECT_ID.iam.gserviceaccount.com` | Custom `projects/PROJECT_ID/roles/sdpContentUse`, only `serviceusage.services.use` | Project content-use permission; not DLP-only IAM. |

The future WIF plan must replace only the exact current source-SHA condition with
the one final qualified preparation commit. Do not accept both SHAs, remove the
pin or add wildcards. Preserve issuer, attribute mapping, immutable owner/repository
IDs, exact repository, main/ref type, `workflow_dispatch`, protected environment
subject, workflow path and all IAM bindings. Unexpected changes or refresh
differences stop execution for review; the earlier completed execution's specific
metadata-refresh approval does not authorize new drift. Verify live before/after
policy after applying the one successfully reviewed saved plan.

GitHub environment `google-sdp-evaluation-release` remains owner-reviewed,
`prevent_self_review=false`, main-only and `can_admins_bypass=false`. This retains
the explicit synthetic owner-review amendment; it is not independent review.
Reverify protection settings and secret **names only**. No protection weakening,
reviewer/admin waiver or credential addition is proposed. Release uses the existing
SHA-pinned actions, private Docker configuration lifecycle and short-lived GitHub
OIDC/WIF path; no JSON keys or stored access/OIDC tokens.

## Required future execution order

1. Obtain one owner approval binding the final source, fresh qualification subjects,
   exact private names, inventory/IAM, existing governance/network amendments,
   two-attempt limits, costs and cleanup. Previous executions do not authorize this
   new release or diagnostic run.
2. Reverify authenticated inventory, region/version eligibility, private state,
   enabled API contracts, registry immutability, zero user-managed evaluation keys,
   current WIF/IAM/protections and absence of owned active evaluation infrastructure.
   Cloud Shell availability/authentication is not established by worker preparation;
   complete any required owner browser authentication/release review handoff.
   Never transfer credentials, ADC, raw state or plans to the worker.
3. Use retained native backend prefixes `portfolio/google-sdp-evaluation` and
   `portfolio/google-sdp-evaluation-cluster`. Save complete private binary plans,
   hash them, review sanitized exact actions and apply that same saved file only.
   Do not apply an incomplete plan, unrelated difference or unexpected refresh.
4. Review the fast-forward push; apply only the reviewed SHA-pin update. Dispatch
   **one** existing manual release with `evaluation_profile=context-001-diagnostic-v1`,
   `region=us-east1`, `artifact_repository=sdp-evaluation-images`,
   `image_name=google-sdp-context-diagnostic` and the exact source commit. Locks,
   tests, input hashes, selected-builder archive export/load, diagnostic-only
   offline run, reproducible configuration, fresh SBOM/scan and unchanged
   zero-exception vulnerability policy precede registry authentication.
5. Require the protected publish rebuild to reproduce the qualified configuration.
   Push the immutable commit-derived tag, resolve and pull its actual manifest,
   compare configuration, produce fresh digest-linked SBOM/scan/policy and keyless
   sign/verify **the exact digest**, not a mutable tag. Verify GitHub issuer,
   workflow identity, exact source and `workflow_dispatch` extensions. An existing
   historical signature signs its historical image, not the new preparation source.
6. Recheck exact REGULAR `1.35.8-gke.1225000` availability; stop if unavailable.
   Review a successful cloud-backed creation plan containing only eight temporary
   creates and retained node-GSA enablement. Record creation time/partial resources
   before apply. Preserve one private `e2-standard-2`/20 GiB pd-balanced node,
   bounded transient default-pool removal, VPC-native Dataplane V2/native FQDN,
   kube-dns without NodeLocal, GKE metadata and Shielded settings. Control-plane
   minimum and managed-pool version contracts remain unchanged. No upgrade is
   selected to bypass a gate.
7. Render with the [dedicated diagnostic renderer](../../scripts/render-sdp-context-diagnostic-job.sh)
   using trusted project, exact runtime GSA and verified diagnostic image digest.
   Run the [diagnostic validator](../../scripts/validate-sdp-context-diagnostic-deployment.py)
   and native API/schema/admission dry-runs. Neither script applies anything;
   the full-campaign renderer is not an acceptable diagnostic execution subject.
8. Apply only reviewed controls and scoped logging, then complete the genuine
   zero-SDP-call network preflight below. Delete probe Job/Pod/ConfigMap and verify
   one-Pod/Job quota is free. Create the validated diagnostic Job **suspended**,
   read back its exact settings and unsuspend once only after all gates pass.
9. Retain schema-valid sanitized result, fixed case/policy identity, diagnostic
   code/stage/status, operation counts, timing and native imageID. On failure,
   report the bounded code and stop without a release/Job/provider retry. Then
   perform and verify cleanup. A pass authorizes no full campaign, live-agent
   request or Presidio authority/removal action.

## Kubernetes and genuine network preflight

Namespace/KSA remain `google-sdp-evaluation` / `google-sdp-evaluation`. Render eight
inherited controls: Namespace, KSA, ConfigMap, diagnostic Job, NetworkPolicy,
FQDNNetworkPolicy, ResourceQuota and LimitRange, plus the separate existing scoped
NetworkLogging/probe ConfigMap/Job. Restricted PSA; UID/GID 65532, nonroot,
read-only root, no privilege escalation, drop ALL, RuntimeDefault seccomp; CPU
100m/500m, memory 128/512 MiB, temporary storage 64/256 MiB, zero writable volume.
No Secret, added RBAC, port, hostPath, host network/PID/IPC or production namespace.

The ConfigMap contains only fixed non-sensitive region/endpoint/corpus path.
Trusted rendering supplies project identity and GSA annotation. The dedicated
validator rejects altered arguments, acknowledgements, retries, command/input
selectors, limits, identity or security controls. It does not establish provenance
of any arbitrary digest; registry/configuration/signature verification is separate.

Allow only cluster kube-dns TCP/UDP 53, metadata `169.254.169.254:80` and native
DNS-derived `dlp.us-east1.rep.googleapis.com:443`. The application pins the same
endpoint and processing parent `projects/PROJECT_ID/locations/us-east1`. No broad
HTTPS/IP rule, proxy, endpoint substitution or regional fallback is proposed.
Before unsuspension require:

- Metadata **email only** matching the runtime GSA; no token output or SDP call.
- Approved endpoint DNS resolution and verified TLS certificate/HTTP2 on its
  derived destination IP.
- Genuine denied TCP connections to two non-overlapping unrelated resolved HTTPS
  destinations, those two direct IPs, `8.8.8.8:443` and `8.8.8.8:53/TCP`.
- Matching native datapath ALLOW/DENY verdicts for each required allow/deny, bound
  to destination/port/source/identity/timestamp. A timeout, missing route or
  injected socket result alone is not enforcement evidence. Missing CRD/verdict
  support or an allowed prohibited route blocks the run; do not enable broader
  logging or weaken policy.

The retained native IP/port amendment is explicit: standard NetworkPolicy cannot
enforce an FQDN; native FQDN policy derives IPs from DNS and cannot isolate Layer-7
hostnames, other APIs sharing an allowed IP or queried DNS names. Application
pinning/TLS verification remain mandatory. Project workload-pool reuse does not
establish cluster-specific identity isolation. These limitations are not waived.

## Costs, cleanup and evidence retention

Recheck current regional prices before execution. Preserve the previous conservative
USD 0.22/hour allowance for node/control-plane/disk/NAT-IP, approximately USD 0.44
for two hours, plus transient default-pool compute, NAT processing, transfer,
registry/state/log/request charges. This retained planning allowance is not a new
price quote or reconciled bill. Do not assume free management credits. Registry
growth/transfer remain bounded at 1 GiB each and logs at 100 MiB. Include the two
content attempts and [SDP minimum billing units](https://cloud.google.com/sensitive-data-protection/pricing);
attempt counters do not prove server receipts, transformed bytes or billed usage.

**USD 5 is an incremental operator stop rule, not a guaranteed billing cap.**
Existing worker/MASAR and previously retained storage costs are outside this run.
The operator/connected agent starts cleanup by minute 90 from first creation apply
or immediately on failure, targeting verified deletion by two hours. Partial
provisioning starts the same clock. No automated cluster expiry exists; the owner
must resume or take over cleanup after disconnect. Job TTL is not cluster cleanup.

Retain sanitized evidence before workload deletion and download fresh release
artifacts before their 14-day expiry. Preserve bounded diagnostics/result, release
digest/configuration and exact-source signature verification, fresh scan/SBOM/policy,
native schema/identity/network evidence, reviewed plan summaries, timing and verified
cleanup for 90 days. No raw response/text/exception, token, credential file or raw
Terraform state/plan belongs in downloadable or committed evidence.

Delete only owned probe/diagnostic workloads, namespace/scoped logging and the eight
temporary resources through the reviewed saved cleanup plan. Remove temporary node
system-role binding and disable the retained node GSA. Verify actual absence of
cluster/pools/VMs/disks/MIGs, VPC/subnet/router/NAT/address/firewalls/routes and any
partial creation. Remove new private credentials/plans/backend caches after retaining
sanitized summaries; preserve platform-managed authentication and unrelated workspaces.

Retain both private current states/bucket/version/soft-delete/lifecycle controls,
identities/WIF/custom role/approved bindings/shared APIs, inactive node reader,
disabled node GSA, historical and new immutable images/signatures, protected GitHub
configuration and private evidence. Retained registry/state/log storage can keep
costing. No implicit old-image deletion, immutable-tag weakening, shared-API
disablement, MASAR change or worker/UI interruption is authorized.

## Decision boundary and remaining UNKNOWNs

This milestone diagnoses only the first failed-closed case. Even a pass does not
resolve the historical cause conclusively or qualify the remaining 85 cases,
finite Arabic/English variants, unsupported boundaries, full eight-class campaign,
safe valid identifiers, span precision/recall, preservation, statistics/truncation,
Unicode/obfuscation/OCR behavior, latency or repeated-agent budgets.

Privacy/processor/location review, durable audit, detector drift, independent review,
live gateway/model/scoped-client credential and trusted identity/tenant/database
integration, a separate provider-selection ADR and retirement decision remain gates.
Historical state-read/version, IAM-delta, impersonation/signed-URL/worker-credential
and transient bootstrap-node UNKNOWNs remain recorded. No accuracy, Saudi residency,
production, Presidio-replacement or full-CS6 claim follows. Zero scan findings do
not establish universal secret protection.
