# Proposed context-060 comparison diagnostic

**Prepared only; one new execution approval is required.** The
[offline assessment](google-sdp-context-email-diagnostics.md) found no justified
detector or adapter repair. This proposal measures four fixed synthetic comparisons
and cannot qualify the failed campaign or enable agents. The final private owner
handoff binds the committed program/renderer/validator hashes, source SHA, exact
existing project/number/bucket and identities. `PROJECT_ID`, `PROJECT_NUMBER` and
`REPOSITORY_ID` below denote only those existing reviewed subjects.

## Fixed inputs and limits

| Comparison ID | Fixed input and reason |
| --- | --- |
| `context-060` | Exact unchanged frozen mandatory fixture; amount label with reserved `example.invalid` email. |
| `email-label-control` | Same value with `Email:` label; changes label only. |
| `reserved-domain-control` | Same amount label/local part with reserved `example.com`; changes domain only. |
| `numeric-retention-control` | Fixed mixed English/Arabic numeric-only SAR amounts and date; no email, entire text must survive. |

The [diagnostic program](../../scripts/diagnose-sdp-email-context.py) derives the
first three subjects from hash-verified frozen corpus/policy, not arbitrary input.
The fourth is the exact committed numeric control. No full campaign, arbitrary
case/text/file, threshold, endpoint or credential selector exists. All comparisons
use `POSSIBLE`, original type mapping and existing transformation/byte/deadline
guards. Neither amount-labelled acceptance nor case classification changes.

- **One diagnostic Job/Pod**, four comparisons in that order; at most four inspect
  plus four deidentify invocation attempts, **eight content attempts total**.
  Failed invocations consume the same shared budget. Zero metadata SDP SDK calls.
- Zero SDK/application/Job retries or automatic release/diagnostic/full rerun.
  `retry=None`; input/output 4,096 UTF-8 bytes, RPC three seconds, combined
  monotonic redaction eight seconds; diagnostic admission 60 seconds.
- Suspended `google-sdp-email-diagnostic`; 120-second active deadline,
  parallelism/completions one, backoff zero, restart Never, completion TTL 3,600.
- Exactly the committed Python program as `-c` plus `--live`, both ACKs:
  `PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK=I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY`
  and `PORTFOLIO_SDP_EMAIL_DIAGNOSTIC_ONLY_ACK=I_ACKNOWLEDGE_FOUR_EMAIL_COMPARISONS_EIGHT_ATTEMPTS`.
  ACKs are admission controls, not owner execution approval.

Each completed row is **OBSERVATION**, with tp/fp/fn, total findings, returned
likelihood histogram and provider-output-guard status. A scoring mismatch proceeds
only to the remaining explicitly approved diagnostic controls. It is never a
mandatory campaign pass or permission to continue the campaign. Any RPC, malformed
response, guard, deadline or budget failure stops immediately with bounded finite
code/stage/status and triggers cleanup. No follow-up diagnostic call is implied.
Empty likelihood totals cannot distinguish no candidate from below-threshold
candidates. All comparisons are descriptive; no historical-cause or causal proof.

Results have scope `context_060_four_comparisons_only`; final outcome is
`DIAGNOSTIC_ONLY_REVIEW_REQUIRED` or `FAIL_CLOSED`, never campaign `PASS`.
The program's bounded duplicate-key/UTF-8 result admission rejects raw or extra
fields, reordered/missing nonterminal rows, invalid likelihood enums, incorrect
counts and accounting. Results are at most 4,096 bytes. No raw text, values,
findings, quotes, spans, per-text hashes, responses, exception messages or
credentials are retained; ephemeral spans are cleared after scoring.

## Exact unchanged image and separate program provenance

Reuse the **already signed campaign image**, image source
`de9f3d1d8a5ae83f0d1fa88ac5f3e35daa1f4639`:

```text
us-east1-docker.pkg.dev/PROJECT_ID/sdp-evaluation-images/google-sdp-context@sha256:667ceec4b8290df1341a91a7685ad140319fca6d23f92b9948dddf9fac64136b
```

Configuration `sha256:23245487ba8c7bfd616e15ff827fdfa85884dd5d15295240dd1035e22b55b90a`;
archive `15cfb18d1088745094e3cf543fef46d9c245d870c9534147899544c80cd87a14`;
[campaign qualification](../../evaluation/google-sdp-context/campaign-qualification.json)
SHA256 `8fdd95d306a3d194daba5e53aa85c5709e6714d268d0ca62b31cb4a5ea1d7d3b`.
All 14 recorded image inputs remain byte-identical. Policy hash
`c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db` and corpus hash
`0c07aa1e8b480e732cdcaa6e9f406661058220ad41de607af7124198e5e71eb9` remain frozen.
The existing scan/SBOM qualify those unchanged bytes; changed image inputs would
require fresh qualification and a revised bundle before execution.

**The new program is outside the image. The image signature does not sign it.**
The approval must separately bind its exact source hash and canonical rendered
command/Job. The renderer includes a program-hash annotation and the validator
requires byte-exact program contents, fixed command and digest. No dynamic download,
shell, extra volume, writable path or arbitrary command is admitted. Worker
network-none execution in the retained image checks program compatibility only.
The program's separate source review/secret scan is not image-signature evidence.

Before creation, native authentication must freshly verify exact manifest/config,
GitHub issuer/workflow/source/extensions and unchanged immutable registry/IAM;
obtain a current exact-digest scan/SBOM/unchanged zero-exception policy result.
Scanner metadata retrieval is not a diagnostic SDP call. Stop on new HIGH/CRITICAL
findings; do not publish or weaken policy to bypass them.

**No WIF change, push, workflow dispatch, image rebuild/publication or signing is
proposed.** Reverify and preserve WIF's exact `de9f3d1d…` source pin and every
trust condition/mapping. The separately approved diagnostic source is transferred
privately and hash-verified; it is not accepted as a release identity. Preserve
main-only environment, owner reviewer/self-review limitation and no admin bypass.

## Enumerated infrastructure and IAM

Same **24 Terraform resources plus retained state bucket**. Terraform 1.16.5,
locked Google 8.5.0 and both retained backend prefixes remain. No API enablement,
import, upgrade, billing change, new identity or unrelated deletion is included.

| Terraform address | Exact existing name or binding | Disposition |
| --- | --- | --- |
| `google_project_service.artifact_registry` | `artifactregistry.googleapis.com` | Retain enabled contract. |
| `google_project_service.sdp` | `dlp.googleapis.com` | Retain enabled contract. |
| `google_project_service.iam_credentials` | `iamcredentials.googleapis.com` | Retain enabled contract. |
| `google_project_service.sts` | `sts.googleapis.com` | Retain enabled contract. |
| `google_artifact_registry_repository.evaluation` | `sdp-evaluation-images`, us-east1, immutable | Read/reuse; retain all images/signatures. |
| `google_service_account.release` | `google-sdp-release` | Retain; publication path unused, no keys/change. |
| `google_service_account.runtime` | `google-sdp-runtime` | Reuse; retain, no keys. |
| `google_iam_workload_identity_pool.release` | `google-sdp-release` | Retain unchanged. |
| `google_iam_workload_identity_pool_provider.github` | `github-release` | Retain exact old image-source SHA; no update. |
| `google_artifact_registry_repository_iam_member.release_writer` | Release repository writer | Retain unused binding. |
| `google_artifact_registry_repository_iam_member.node_reader` | Node repository reader | Reuse; retain inactive after node disablement. |
| `google_service_account_iam_member.github_release_impersonation` | Repository-ID federation on release GSA | Retain unchanged, unused. |
| `google_service_account_iam_member.gke_runtime_impersonation` | Evaluation namespace/KSA on runtime GSA | Reuse; retain. |
| `google_project_iam_custom_role.sdp_content_use` | `sdpContentUse`, only `serviceusage.services.use` | Retain unchanged. |
| `google_project_iam_member.runtime_content_use` | Runtime custom-role binding | Reuse; retain. |
| `google_compute_network.evaluation[0]` | `google-sdp-evaluation` VPC | Create/delete. |
| `google_compute_subnetwork.evaluation[0]` | `google-sdp-evaluation`, us-east1 | Create/delete. |
| `google_compute_address.nat[0]` | `google-sdp-evaluation-nat`, us-east1 | Allocate/release. |
| `google_compute_router.evaluation[0]` | `google-sdp-evaluation`, us-east1 | Create/delete. |
| `google_compute_router_nat.evaluation[0]` | `google-sdp-evaluation` new-subnet-only NAT | Create/delete. |
| `google_service_account.node` | `google-sdp-evaluation-node` | Enable retained disabled account; disable after cleanup. |
| `google_project_iam_member.node[0]` | Node `roles/container.defaultNodeServiceAccount` | Create/remove temporary project binding. |
| `google_container_cluster.evaluation[0]` | `google-sdp-evaluation`, us-east1-b | Create/delete including partial creation. |
| `google_container_node_pool.evaluation[0]` | `evaluation`, us-east1-b | Create/delete with VM/disk/MIG. |
| Separate private bucket | Exact existing name in owner handoff, us-east1 | Retain current states/version/soft-delete/lifecycle and nonpublic IAM. |

Release writer/node reader remain repository-scoped. Runtime federation remains
`serviceAccount:PROJECT_ID.svc.id.goog[google-sdp-evaluation/google-sdp-evaluation]`
with `roles/iam.workloadIdentityUser` on the runtime GSA. Release federation remains
the exact numeric repository-ID principal set in existing pool `google-sdp-release`.
Runtime custom permission is project-level content usage, **not DLP-only IAM**.
Project-wide workload-pool reuse **does not establish cluster identity isolation**.
Existing owner administration is reused; no new grant or least-privilege claim.

## Future gates and exact order

1. One owner approval binds final source, program/renderer/validator and unchanged
   image subjects, four comparisons/eight-attempt limits, resource/IAM contract,
   limitations, cost amendments and cleanup. Earlier campaign approval is exhausted.
2. Fresh native authenticated inventory: exact project/number/location policy,
   enabled APIs, private state/bucket IAM, immutable registry/policies, WIF/IAM,
   zero evaluation keys, disabled node account and zero owned evaluation resources.
   Native Cloud Shell/authentication and inventory are not verified by preparation.
   No credentials, ADC or raw state/plans go to worker, Git or downloadable evidence.
3. Verify unchanged image/provenance/current scan gates and exact separate program
   hash. Identity-root plan must have no changes/refresh drift and is not applied.
   Stop on unexpected drift/refresh; particular historical waivers do not carry over.
4. Native cluster root uses `project_id`, `gke_version=1.35.8-gke.1225000` and
   `evaluation_cluster_enabled=true`, retained prefix
   `portfolio/google-sdp-evaluation-cluster`; identity prefix remains
   `portfolio/google-sdp-evaluation`. Recheck exact REGULAR version availability;
   never choose another version. Review/hash complete successful saved creation
   plan: eight creates and node enablement only. Record first creation time before
   applying exactly that file once. No incomplete/unrelated plan applies.
5. Dedicated private e2-standard-2 node/20 GiB pd-balanced, bounded transient default
   pool removal, existing private IPv4/Pod/service ranges, VPC-native Dataplane V2/
   FQDN, kube-dns/no NodeLocal, DNS-IAM-only control plane, Shielded/GKE_METADATA
   settings remain. No node auto-repair or upgrade authorizes another Job.
6. Render using the dedicated [renderer](../../scripts/render-sdp-email-diagnostic-job.sh)
   with trusted project/runtime GSA and exact signed digest; run the
   [validator](../../scripts/validate-sdp-email-diagnostic-deployment.py), native
   schema/admission dry-runs and command/program/hash review. Apply only controls
   and scoped logging, then complete genuine zero-SDP network preflight below.
7. Delete preflight Job/Pod/ConfigMap, verify one-Job/Pod quota free. Create the
   exact diagnostic Job suspended, read back command/program/hash/digest/ACKs,
   limits/security/identity; unsuspend once. No recreation or automatic rerun.
8. Retain minimized validated result, timing/imageID and accounting before deletion.
   Code/guard/unknown gate failure stops immediately. Scoring mismatches remain
   diagnostic observations; after at most four fixed comparisons, stop and clean up.
9. Review/apply one complete saved cleanup plan with
   `evaluation_cluster_enabled=false`: eight owned deletes plus node disablement.
   Verify actual absence and preserved identity/WIF/registry/state boundaries.

## Kubernetes, genuine network checks and limitations

Namespace/KSA `google-sdp-evaluation`/`google-sdp-evaluation`; eight inherited
Namespace/KSA/ConfigMap/Job/NetworkPolicy/FQDNNetworkPolicy/ResourceQuota/LimitRange
objects, plus existing scoped NetworkLogging and hashed probe ConfigMap/Job.
Restricted PSA, UID/GID 65532, nonroot/read-only/no escalation/drop ALL/RuntimeDefault;
CPU 100m/500m, memory 128/512 MiB, temporary storage 64/256 MiB. No app volume,
Secret, port, extra RBAC, host path/network/PID/IPC or production namespace.

Deny ingress. Allow kube-dns TCP/UDP 53, metadata `169.254.169.254:80` and native
DNS-derived `dlp.us-east1.rep.googleapis.com:443` only. Same regional parent
`projects/PROJECT_ID/locations/us-east1`, no proxy/fallback/broad HTTPS/IP rule.
Before diagnostic unsuspension require metadata **email only** matching runtime GSA,
approved DNS resolution plus regional TLS certificate/HTTP2 success, and six genuine
denied TCP observations: two non-overlapping unrelated resolved HTTPS destinations,
those direct IPs, `8.8.8.8:443` and `8.8.8.8:53/TCP`. Match native ALLOW/DENY
verdicts by source/destination/port/time with Kubernetes/KSA/metadata correlation.
Timeout/missing route/injected results alone are not enforcement proof. Missing
CRD/verdict/denial support stops; no broader logging or permission workaround.

DNS-derived IP/port policy cannot isolate Layer-7 hostnames, other APIs sharing
allowed IPs or DNS query names. Application/TLS pinning remains mandatory. Metadata
email alone is not proof of SDK authentication. Preserve these limitations and
owner self-review, historical audit/credential/transient-bootstrap UNKNOWNs.

## Costs, cleanup, retention and decision

Carry forward removal of the USD5 threshold and billing screenshot/trial-credit
prerequisite; no balance, expiry or eligibility is assumed. New approval accepts
only this diagnostic's cost; **no billing upgrade/change** or extra campaign/resource.
Recheck current regional SKUs without changing billing. Historical USD0.22/hour
planning allowance is not a current quote or cap. Include transient/default-pool,
NAT/disk/transfer/log/state/registry/request costs; bounded transfer at most 1 GiB,
logs at most 100 MiB. Invocation counters do not prove receipts or billed usage.

Cleanup begins **immediately on operational/gate failure**, after completed diagnostic
observations, or by **minute90 from first creation including partial resources**.
Verify deletion by **two hours**. Operator-managed lifetime has no automatic expiry;
owner takeover after disconnect is mandatory. Job TTL is not cluster cleanup.
Remove owned workloads/namespace/scoped logging, eight temporary resources/system
role; disable node. Verify cluster/pools/VMs/disks/MIGs/unmanaged groups and
VPC/subnet/router/NAT/address/firewalls/routes absent, including partial creation.
Remove new private plans/backend caches/renders/auth files only after minimized
retention receipts and ownership/type/permission checks; preserve platform auth,
worker/UI, MASAR and original workspaces. Preserve state/bucket/identities/WIF/API/
registry/images/signatures; retained storage may continue costing. Charges unknown.

Keep minimized hashes/validation/network/provenance/timing/accounting/cleanup for
90 days, downloading before any artifact expiry. No new release artifacts are
created by this proposal. Historical 59 passes and failed campaign evidence remain
unchanged and do not become qualified through this diagnostic.

No full rerun, revised detector, valid-ID research, real data, model/LiteLLM request,
agent enablement, provider selection, Presidio remediation/deletion/retirement or
fallback follows any outcome. Exact next gates remain finite policy acceptance and
unexecuted boundaries, processor/privacy/location/independent review, provider-neutral
runtime/byte/repeated-turn budget/latency/audit qualification, actual identity/tenant/
database and scoped LiteLLM/gateway/model/service qualification, separately approved
synthetic end-to-end agents, then explicit authority/consumer/rollback decisions.
