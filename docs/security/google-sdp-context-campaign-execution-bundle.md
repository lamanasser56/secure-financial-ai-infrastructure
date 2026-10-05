# Frozen context-pattern-v1 campaign continuation proposal

**Preparation only; new campaign execution approval is required.** This is one SDP-only campaign,
not a live-agent/Vertex bundle or Presidio replacement decision. Exact source SHA,
private project/account identifiers and state bucket are bound in the final owner
handoff outside Git. `PROJECT_ID` below denotes only that previously reviewed
evaluation project; no alternate project, region or new identity is selectable.

## Completed diagnostic and preparation boundary

The diagnostic at source `168edaea8d2e19324dc08668a709b6c68531a20c` passed its
one English national-ID context case with two attempted SDK operations and no
retries. Temporary cloud and task-private cleanup was verified on 2026-10-05.
These are historical facts, not fresh inventory for this proposal. The historical
first campaign's precise failure cause remains UNKNOWN; the bracketed replacement
compatibility defect was confirmed independently and its adapter repair is reused.

The frozen policy/corpus and adapter remain unchanged. Only the campaign harness
and result-schema image inputs change: operational failure accounting, finite
deadline diagnostics and aggregate integrity checks. Fresh builds/scans qualify
these bytes. No provider call, cloud mutation, publication or push occurs in
preparation. Presidio remains authoritative; remediation and the separate
valid-identifier/eight-class research campaign remain paused. The UI stays offline.

## Frozen subjects and limits

| Input | Exact proposed subject |
| --- | --- |
| Policy | `context-pattern-v1`; hash `c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db` |
| Corpus | 86 committed synthetic cases; hash `0c07aa1e8b480e732cdcaa6e9f406661058220ad41de607af7124198e5e71eb9` |
| Local image configuration | See the fresh `campaign-qualification.json` record and exact private handoff. |
| Matching Docker archives | Two fresh byte-identical archives; hashes bound in that record and private handoff. |
| Intended registry image | `us-east1-docker.pkg.dev/PROJECT_ID/sdp-evaluation-images/google-sdp-context` |
| Registry manifest and signature | Not created; resolve after one separately approved release; never substitute local configuration as manifest digest |
| SDK budget | At most 86 inspect + 86 deidentify = **172 attempted content operations**; zero metadata SDK calls |
| Per redaction | Input/output 4,096 UTF-8 bytes; RPC three seconds; combined monotonic eight seconds |
| Campaign | One Job, 900 seconds, zero SDK/application/Job retries; stop on first required failure/provider guard/deadline/budget failure |
| Acceptance | 70 exact-span/preservation mandatory cases; 16 explicitly unsupported observations; no promotion decision inferred |
| Temporary infrastructure | Two hours from first creation apply, cleanup starts by minute 90 and immediately after any failing gate |

The [qualification artifact](../../evaluation/google-sdp-context/campaign-qualification.json)
binds all 14 image inputs and fresh local scan/SBOM, KEV and secret evidence. No old seed or gateway scan
qualifies these bytes. Historical seed, original campaign and diagnostic records remain unchanged;
their manifests/signatures do not qualify this new image. The diagnostic release
helper rejects the changed inputs before build/authentication; no new diagnostic
publication is included.

## Result and stop contract

New results explicitly carry `scope=context_pattern_v1_campaign`. Only mandatory
`PASS`/`FAIL`/`FAIL_CLOSED` cases contribute to `required_pass`/`required_fail`.
A completed unsupported case is `OBSERVATION`, irrespective of detections; its
counts are observation-only, excluded from mandatory precision/recall. An
unsupported-case provider/guard failure is `FAIL_CLOSED` with
`observation_failures=1` and `operational_failures=1`, without fabricating a
mandatory failure. It still stops execution immediately and fails the campaign,
independently of the remaining case count. Mandatory guard failures remain
mandatory failures and operational failures. Zero tp/fp/fn on FAIL_CLOSED are
placeholders, not detection scores.

A between-case 900-second deadline emits only
`campaign_diagnostic={code:OVERALL_TIMEOUT,stage:sequence}` and stops before
another dispatch; it does not invent a failed accuracy case. The shared budget
continues counting every attempted SDK call, including failures, with `retry=None`.
Offline injected calls are reported separately and never labelled SDK/provider
receipts. Case order, status/classification, counts, first-failure stop and attempt
ceilings are validated; historical scope-less schema-v1 results remain readable.
Use `python scripts/validate-sdp-context-campaign-result.py RESULT.json` to check
bounded UTF-8/duplicate-key input, frozen IDs/order/aggregates/attempts and new scope;
it accepts neither a one-case diagnostic nor an old scope-less result as the new
campaign. It reports a sanitized contract failure without the rejected content.
Historical results remain readable with the original schema/harness validator.
Reports retain only finite IDs/counts/status/diagnostics, no text, values, spans,
quotes, per-text hashes, responses, exception messages or credentials. Native
operator tooling must likewise minimize logs and check schema before retention.

Campaign acceptance requires all 70 mandatory exact-span/preservation passes,
zero mandatory or operational failures, all 16 unsupported observations reported
separately and no unexecuted case. This is finite frozen policy acceptance only.
Any failure or unknown execution/provenance/network gate causes safe cleanup;
report the finite case diagnostic if available and **stop without a rerun**.

## Exact resource inventory

Reuse existing private state/bucket and 15 identity-root resources after fresh
inventory. Create only the eight previously removed cluster resources below and
temporarily enable the retained node account. This preserves the existing total
inventory of **24 Terraform resources plus the separately retained state bucket**.
No state-bucket bootstrap, new API enablement, billing change, resource import,
provider upgrade, new role or unrelated deletion is proposed. Terraform/provider
remain 1.16.5 / locked Google 8.5.0. On unexpected live drift, stop before apply.

| Resource type/address | Exact name | Location | Action / cleanup |
| --- | --- | --- | --- |
| `google_project_service.artifact_registry` | `artifactregistry.googleapis.com` | Project | Reuse enabled contract; retain. |
| `google_project_service.sdp` | `dlp.googleapis.com` | Project | Reuse enabled contract; retain. |
| `google_project_service.iam_credentials` | `iamcredentials.googleapis.com` | Project | Reuse enabled contract; retain. |
| `google_project_service.sts` | `sts.googleapis.com` | Project | Reuse enabled contract; retain. |
| `google_artifact_registry_repository.evaluation` | `sdp-evaluation-images` | us-east1 | Reuse immutable repository; retain new image/signature and all historical images/signatures. |
| `google_service_account.release` | `google-sdp-release` | Project | Reuse; no keys; retain. |
| `google_service_account.runtime` | `google-sdp-runtime` | Project | Reuse; no keys; retain. |
| `google_iam_workload_identity_pool.release` | `google-sdp-release` | global | Reuse; retain. |
| `google_iam_workload_identity_pool_provider.github` | `github-release` | global | Replace only exact source-SHA condition with final approved commit; retain all other conditions/mapping. |
| `google_artifact_registry_repository_iam_member.release_writer` | Release GSA writer binding | us-east1 repository | Reuse; retain. |
| `google_artifact_registry_repository_iam_member.node_reader` | Node GSA reader binding | us-east1 repository | Reuse; retain inactive after node disable. |
| `google_service_account_iam_member.github_release_impersonation` | Repository-ID federation binding | Release GSA | Reuse; retain. |
| `google_service_account_iam_member.gke_runtime_impersonation` | Namespace/KSA federation binding | Runtime GSA | Reuse; retain. |
| `google_project_iam_custom_role.sdp_content_use` | `sdpContentUse` | Project | Reuse only `serviceusage.services.use`; retain. |
| `google_project_iam_member.runtime_content_use` | Runtime custom-role binding | Project | Reuse; retain. |
| `google_compute_network.evaluation[0]` | `google-sdp-evaluation` | global | Create dedicated VPC; delete. |
| `google_compute_subnetwork.evaluation[0]` | `google-sdp-evaluation` | us-east1 | Create dedicated subnet/ranges; delete. |
| `google_compute_address.nat[0]` | `google-sdp-evaluation-nat` | us-east1 | Create single NAT IP; release. |
| `google_compute_router.evaluation[0]` | `google-sdp-evaluation` | us-east1 | Create; delete. |
| `google_compute_router_nat.evaluation[0]` | `google-sdp-evaluation` | us-east1 | Create new-subnet NAT only; delete. |
| `google_service_account.node` | `google-sdp-evaluation-node` | Project | Reuse disabled account, enable temporarily; disable after cleanup. |
| `google_project_iam_member.node[0]` | Node system-role binding | Project | Create temporarily; remove. |
| `google_container_cluster.evaluation[0]` | `google-sdp-evaluation` | us-east1-b | Create dedicated temporary cluster; delete. |
| `google_container_node_pool.evaluation[0]` | `evaluation` | us-east1-b | Create one node; delete with boot disk/MIG. |
| Separate retained state bucket | Exact private handoff name, same as completed campaign | us-east1 | Reuse private current states/version/soft-delete/lifecycle controls; retain, continuing cost. |

## IAM, identity and governance

| Principal | Exact role/permissions | Resource scope and purpose |
| --- | --- | --- |
| Existing authenticated owner/operator | Existing project Owner authorization; **no additional grant** | Native Cloud Shell/saved-plan administration. Not a least-privilege operator claim. |
| `serviceAccount:google-sdp-release@PROJECT_ID.iam.gserviceaccount.com` | `roles/artifactregistry.writer` | Evaluation repository only; publication. |
| `serviceAccount:google-sdp-evaluation-node@PROJECT_ID.iam.gserviceaccount.com` | `roles/artifactregistry.reader` | Same repository only; image pull. |
| Same node GSA | `roles/container.defaultNodeServiceAccount` | Project; temporary existing minimum node-system permission contract. No content calls. |
| `principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/google-sdp-release/attribute.repository_id/REPOSITORY_ID` | `roles/iam.workloadIdentityUser` | Release GSA only; exact GitHub claims additionally enforced by provider. |
| `serviceAccount:PROJECT_ID.svc.id.goog[google-sdp-evaluation/google-sdp-evaluation]` | `roles/iam.workloadIdentityUser` | Runtime GSA only. Project-pool identity reuse remains a limitation. |
| `serviceAccount:google-sdp-runtime@PROJECT_ID.iam.gserviceaccount.com` | Custom `projects/PROJECT_ID/roles/sdpContentUse`, only `serviceusage.services.use` | Project; content-call usage permission is not DLP-only. Network/application gates remain necessary. |

WIF pool/provider, issuer, mapping, numeric owner/repository IDs, exact repository,
main branch/ref type, `workflow_dispatch`, protected environment subject and exact
workflow path stay unchanged. Future SHA-only saved plan must update one provider
condition only, accept exactly one final source SHA, and have no refresh/unrelated
differences. Previous approvals of particular metadata refreshes are not inherited. Apply once only after new approval; verify native before/after policy.
The current live source pin remains untouched during preparation.

GitHub environment `google-sdp-evaluation-release`: owner reviewer, self-review
permitted (`prevent_self_review=false`), main branch only, administrative bypass
disabled (`can_admins_bypass=false`). This is the explicit synthetic owner-review
amendment, **not independent review**. Reverify protections/secret names only before
release. Do not grant an admin/reviewer waiver. All action pins, OIDC handling and
private Docker configuration lifecycle remain unchanged.

## Execution order, authentication and saved plans

1. Owner approval binds the final source, frozen policy/corpus/config, exact private
   names, resources/IAM, amendments, new limits and cleanup. Previous full-campaign and diagnostic
   approvals do not authorize this new 172-attempt campaign.
2. Fresh authenticated read-only inventory verifies state access/protections, no
   name collision/active old cluster, account/project/region eligibility, required
   enabled APIs, zero user-managed evaluation keys and current IAM/protections.
   Cloud Shell availability/authentication is **not verified in this preparation**;
   owner completes any required Google authorization or GitHub environment UI.
   Never transfer tokens/ADC/keys/state to the build worker.
3. Native Terraform backend uses retained prefixes `portfolio/google-sdp-evaluation`
   and `portfolio/google-sdp-evaluation-cluster`. Save private binary plans, hash
   them, review only sanitized resource/condition summaries and apply that exact
   reviewed file. No raw state/plan JSON in Git or user output.
4. Review fast-forward push of final source; approve/apply only SHA-pin plan. Dispatch
   **one** existing manual workflow with `evaluation_profile=context-pattern-v1`,
   `region=us-east1`, `artifact_repository=sdp-evaluation-images`,
   `image_name=google-sdp-context` and exact source commit. No automatic rerun.
   Tests/locks, exact input hashes, selected-builder archive, offline run, config
   digest and fresh prepush SBOM/scan/policy precede cloud authentication. Protected
   publish rebuild must reproduce that configuration. Push immutable commit tag,
   resolve/pull/compare actual registry digest, rescan/SBOM/policy then keyless sign
   and immediately verify **that digest**, issuer/workflow/source extensions.
5. Recheck exact `1.35.8-gke.1225000` REGULAR availability. If unavailable, stop;
   do not select a new version automatically. Save cloud-backed cluster plan with
   flag true; eight creates and retained node-GSA enable only, no unrelated drift,
   replacement or permission expansion. Static validation is not a substitute.
6. Record first creation start and partial inventory. Apply reviewed saved plan;
   one steady-state e2-standard-2/20 GiB pd-balanced node, bounded transient default
   pool removed, private IPv4 subnet/Pod/service ranges, VPC-native Dataplane V2,
   native FQDN policy, kube-dns/no NodeLocal, GKE_METADATA and shielded node remain.
   Control-plane minimum version and separate pool version retain the existing
   provider contract; REGULAR upgrades/auto-repair do not authorize more Jobs.
7. Render only with [context renderer](../../scripts/render-sdp-context-job.sh):
   exact project, dedicated runtime GSA and new signed registry digest. No mutable
   tag, alternate region/image or credential input. Native API/schema/server dry-run
   validation precedes applying the reviewed controls-only file. Validate the
   suspended context Job offline/server-side, but do not create it before preflight.
8. Complete the genuine zero-SDP network preflight below, then delete its Job/Pod
   and ConfigMap. Verify the one-Job/one-Pod quota is free before creating the
   **suspended** `google-sdp-context-evaluation` Job; then unsuspend it once.
   Never recreate/retry a failed Job. Preserve
   sanitized result before TTL; stop on first required failure/unknown gate.
9. Cleanup and verify partial resources even after apply failure. Retain evidence,
   result and limitations; no authority change or agent execution follows a pass.

## Kubernetes and network contract

Namespace/KSA: `google-sdp-evaluation` / `google-sdp-evaluation`. Eight inherited
controls: Namespace, KSA, ConfigMap, Job, NetworkPolicy, FQDNNetworkPolicy,
ResourceQuota, LimitRange; separate existing scoped NetworkLogging and hashed probe
ConfigMap/Job. No Kubernetes RBAC/Secret/port/hostPath/host networking is added.
Restricted PSA; UID/GID 65532, nonroot, read-only root, no escalation, drop ALL,
RuntimeDefault seccomp. CPU request/limit 100m/500m, memory 128/512 MiB, temporary
storage 64/256 MiB; zero writable volume. Job suspend true, backoff zero,
parallelism/completions one, deadline 900 seconds, completion TTL 3,600 seconds.
Quota allows one Pod/one Job; delete probe Job/Pod before live Job occupies it.
The context ConfigMap points to its committed corpus. `--live` plus the distinct
context acknowledgement is mandatory; project identity is trusted rendering only.

Network: deny ingress; cluster kube-dns TCP/UDP 53 and metadata
`169.254.169.254:80` only; native DNS-derived `dlp.us-east1.rep.googleapis.com:443`.
Regional SDK processing parent is `projects/PROJECT_ID/locations/us-east1`.
No broad HTTPS/IP-range rule, alternate endpoint or proxy. Before unsuspension:

- Match metadata **email only** to runtime GSA; no token output or SDP request.
- DNS-resolve approved endpoint, verify TLS certificate/HTTP2 on its derived IP.
- Genuine denied TCP connections to two non-overlapping unrelated resolved HTTPS destinations,
  those two direct unrelated IPs, `8.8.8.8:443` and alternate DNS `8.8.8.8:53/TCP`.
- Pair every success/timeout with matching native datapath ALLOW/DENY policy verdicts
  and destination/port/source/identity/timestamp evidence. An unavailable route,
  timeout alone or injected socket result is not enforcement proof. Stop if verdict
  logging, CRD support or required denial is absent; do not enable broader logging.

This retains the explicit native IP/port amendment: standard NetworkPolicy does
not enforce an FQDN; native FQDN policy derives IPs from DNS and cannot establish
Layer-7 hostname isolation, isolate other APIs sharing IPs, or restrict queried DNS
names. TLS/application regional pinning remains mandatory. Project-wide workload
pool reuse is not cluster-identity isolation. These limitations are not waived.

## Cost, cleanup and retention

Content requests have a [1 KB billing minimum](https://cloud.google.com/sensitive-data-protection/pricing).
Conservative calculation ignoring free tiers: the historical rates of 172 × 4 KiB × USD 3/GiB inspection,
plus 86 × 4 KiB × USD 2/GiB transformation is **under USD 0.003**. Deidentify can
also inspect; type replacement may be exempt from transformation charges. Attempts
do not establish server receipts or billing. Actual measured/billed usage is unknown.

Retain the previous conservative USD 0.22/hour node/disk/control-plane/NAT-IP
allowance: two hours about USD 0.44, plus transient default-pool compute, transfer,
NAT processing, registry/state/log/request charges. No free management credit is
assumed. Registry growth/transfer at most 1 GiB each, logs at most 100 MiB. Recheck
current regional SKUs before execution; no claim this old allowance is a price quote.
The owner removed the USD 5 operator threshold and superseded trial-credit/billing
screenshot verification as a prerequisite. Carry both amendments into this proposal;
do not request another screenshot or assume an eligible balance/account status.
Approval would accept only this campaign's cost regardless of trial-credit coverage.
**No billing upgrade/change, additional resource/campaign or guaranteed cap is
included.** Actual charges remain unreconciled. Existing worker/MASAR and previously
retained storage costs are outside the incremental run.

Operator/agent begins cleanup by minute 90 from creation start, immediately on
failure, targeting deletion by two hours. **No automated cluster expiry exists**;
owner must take over on disconnect. Job TTL is not cluster cleanup. Save evidence,
delete owned probe/live workloads/namespace/network logging, review saved cleanup
plan with flag false, remove eight temporary resources/system-role binding and
disable retained node GSA. Verify actual absence of cluster/pools/VMs/disks/MIGs,
VPC/subnet/router/NAT/IP/firewalls/routes and any partial creation. Do not delete unrelated
worker/MASAR or retained identity resources. Remove private new plans/backend
caches/credential files after retaining sanitized plan and cleanup summaries.

Retain both current private states/bucket/version/soft-delete/lifecycle, identities/
WIF/custom role/approved bindings/shared APIs, inactive node reader, disabled node
GSA, historical seed/context/diagnostic subjects plus the new immutable image/signature, GitHub protections and sanitized
evidence for 90 days (download before workflow artifacts expire after 14 days).
Retained registry/state/log storage can continue costing. No implicit image
retirement, immutable-tag weakening, new access or shared-API disablement is allowed.

## Exact integration gates after a possible campaign pass

1. Review the native signed-image/result/attempt/time/network/cleanup evidence and
   explicitly accept or reject this finite policy. Review unsupported observations
   separately. No unrestricted fuzzy matching or comprehensive typo/identifier
   claim follows. The separate 87-case valid-identifier research is not resumed.
2. Decide and document the agents' permitted data classes and unsupported-input
   behavior in a separately reviewed provider-selection/scope ADR. A finite
   context policy does not establish valid-identifier coverage or unrestricted
   free-text detection. Close raw-data processor, privacy, location/retention and
   independent-review gates before accepting real inputs. No Saudi residency claim.
3. Prepare offline integration at the existing provider-neutral TrustedRuntime
   redaction boundary. Preserve neutral categories/errors, pseudonymous tenant
   references, input/output minimization, exact safe-text preservation, finite
   diagnostics, fail-closed behavior and **no automatic fallback**. Test all agent
   ingress/model/tool-result/answer paths, Unicode/obfuscation/truncation/statistics,
   repeated-turn SDK accounting and deadlines inside existing agent budgets.
   Qualify newly changed runtime/service image bytes and detector drift policy.
   The [current runtime boundary](../../runtime/phase3/trusted_runtime.py) still
   uses `presidio_analyzer`/`presidio_anonymizer` trace stages, and
   [AgentCore](../../runtime/agents/core.py) reports `presidio_authoritative`.
   Version those provider-specific trace/report contracts honestly in the later
   integration change; do not label SDP processing as Presidio. The live factory
   in `runtime/agents/demo.py` still constructs Presidio and remains untouched.
   Demonstrate that serialized prompts/history/results fit the SDP 4,096-byte
   bounds without clipping sensitive input. Derive and enforce shared attempted
   SDK budgets for every ingress/history/model/tool-result/final redaction.
   Preserve four-model/four-tool, 60-second turn and 10-second redaction ceilings;
   the [conversation limits](../../runtime/agents/conversations.py) remain eight
   turns, 16 models, 12 tools, 240 execution seconds and 900-second lifetime.
   Conversation reset must not silently renew a live provider spending budget.
4. Independently qualify trusted issuer/subject/tenant server mappings, financial
   database isolation, durable sanitized audit, scoped LiteLLM client keys and
   actual gateway tool-choice protocol/model responses. Every external model call
   must traverse LiteLLM; no master-key agent use or direct provider credential.
   Prepare exact Vertex/keyless gateway identity/region/network/service resources
   and budgets in a separate execution bundle. No agent/model call is authorized
   by this SDP campaign, and mock redaction cannot label a secure live path.
5. Obtain separate approval for bounded synthetic end-to-end agent execution,
   including repeated redaction operations, SDK/model/tool/cost limits, genuine
   identity/network verification, audit, sanitized evidence and cleanup. A UI text
   box/offline demonstration is not live qualification.
6. Only after those gates, decide authority selection explicitly. Inventory all
   Presidio consumers, deployment/config/dependency references and rollback paths
   before a separately reviewed retirement change. Preserve historical evidence.
   The vulnerability-blocked Presidio candidate is not a qualified live rollback;
   if no qualified provider exists, disable live agents and keep the offline demo.
   No deletion or cutover follows a campaign pass.

## Decision and unresolved findings

This bundle measures the new frozen synthetic policy only. No unrestricted live
free-text UI, model request, real record, accuracy claim, Saudi residency, Presidio
fallback/removal/cutover, production or full CS6 closure. Original eight-class/full
87-case qualification, independent review, actual gateway/issuer/key/database,
durable audit and broader network/privacy/detection remain separate gates.
Historical state-read/logging/IAM-delta/impersonation/signed-URL/worker-credential
UNKNOWNs are preserved; source scans do not prove universal secret protection.
