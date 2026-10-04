# Google SDP synthetic live evaluation: gated operator runbook

**Current state:** Historical seed and `context-pattern-v1` signed releases and
bounded live executions completed. The seed recorded six passes and three
inconclusive cases. The context campaign stopped fail closed on `context-001`
after two content SDK invocation attempts, leaving 85 cases unexecuted; its cause
remains UNKNOWN. Historical native cleanup was verified. A separate fixed
first-case diagnostic is prepared for a new approval; it has not been released
or run. Current native inventory/authentication is not established by offline
preparation. Presidio remains authoritative and its remediation remains paused.
This document grants no real-data authorization or provider cutover.

| Gate | Status | Required operator evidence |
| --- | --- | --- |
| 1. Local image qualification | Historical subjects retained; fresh diagnostic subject separate | [Candidate inventory](../../docker/google-sdp-evaluation/candidates.json), historical [context record](../../evaluation/google-sdp-context/qualification.json), fresh [diagnostic record](../../evaluation/google-sdp-context/diagnostic-qualification.json); each binds only its own bytes. |
| 2. GCP identity and registry prerequisites | Historically implemented; fresh read-only checks required | Approved project/budget, private state, existing APIs, exact WIF/IAM and GitHub protections, immutable repository. |
| 3. Manual signed registry release | Historical releases complete; diagnostic release not run | One separately approved release of final diagnostic source through the [manual workflow](../../.github/workflows/release-google-sdp-evaluation.yml). |
| 4. Digest and signature verification | Historical subjects verified; diagnostic subject not proven | New actual registry digest, fresh digest-linked SBOM/Trivy/policy and exact-source Cosign verification. |
| 5. GKE Workload Identity binding | Historically verified; temporary cluster removed | Fresh identity/version inventory and successfully reviewed saved creation plan; same namespace/KSA and node image-pull contract. |
| 6. Synthetic live evaluation | Historical seed/context runs completed; diagnostic not run | Only `context-001` under the [diagnostic execution bundle](google-sdp-context-diagnostic-execution-bundle.md), maximum two content attempts and zero retries. |
| 7. Evidence review and outcome decision | Context qualification failed closed; historical cause UNKNOWN | Minimized result/finite diagnostics, operation counts, verified cleanup; no pass is a replacement decision. |
| 8. Provider-authority change | Prohibited | Separate ADR and explicit approval; this runbook cannot grant it. |

## Dedicated first-case diagnostic profile

The [diagnostic assessment](google-sdp-context-diagnostics.md) separates a confirmed
bracket-format compatibility defect from the UNKNOWN original live cause. Use only
the dedicated [renderer](../../scripts/render-sdp-context-diagnostic-job.sh) and
[validator](../../scripts/validate-sdp-context-diagnostic-deployment.py), with release
profile `context-001-diagnostic-v1` and image `google-sdp-context-diagnostic`.
The suspended Job fixes `--live --diagnostic-first-case`, both synthetic/diagnostic
acknowledgements, maximum two content SDK attempts, zero metadata SDK calls/retries,
4,096-byte input/output, three/eight-second RPC/overall limits and a 120-second Job
deadline. It rejects arbitrary inputs and the full campaign.

One new approval must bind the final qualified source/image, SHA-only WIF update,
one release, exact saved plans/resources, native network evidence and cleanup.
Preparation makes no cloud mutation or provider call. Reverify current native
inventory/authentication and each future digest/signature before execution. The
diagnostic bundle uses a **two-hour** infrastructure lifetime with cleanup starting
by **minute 90** or immediately on failure, preserving the USD 5 incremental
operator stop rule. These are operator-managed limits, not automated guarantees;
owner takeover is necessary after disconnect. A Job TTL does not clean up a cluster.

On diagnostic failure, retain only schema-valid sanitized code/stage/status and
counts, then stop and clean up; do not rerun. On pass, review the result without
starting a full campaign, live agents or Presidio retirement. Historical image
evidence never qualifies changed diagnostic source. No raw data, findings, response
bodies, exception messages or credentials belong in evidence.

The following seed procedures retain their historical preparation/approval context.
Their nine-case, 18-attempt and four-/six-hour bounds must not replace the dedicated
diagnostic bundle's first-case, two-attempt and minute-90/two-hour contract. Historical
status statements are not a fresh cloud inventory or a new execution approval.

## External prerequisites and trust boundaries

The integrated milestone's [readiness record](google-sdp-milestone-readiness.md) distinguishes read-only inventory, source qualification and the single execution-approval checkpoint. The [proposed synthetic execution amendment](google-sdp-synthetic-execution-proposal.md) selects explicit owner approval and a separate native-egress cluster; both amendments remain pending. Owner approval is not independent review and cannot satisfy an independent-review gate. The missing state backend and suspended authenticated operator session have concrete bootstrap paths in the private bundle. VM execution approval alone does not authorize IAM, registry publication or a live Google request.

The operator must select a project and approve the [Terraform GCP bootstrap contract](../../infra/gcp/google-sdp-evaluation/README.md) before any separately authorized provisioning. `artifactregistry.googleapis.com`, `iamcredentials.googleapis.com`, and `sts.googleapis.com` support the release identity path; `dlp.googleapis.com` is needed only for a later synthetic live run. Service Usage, IAM and Resource Manager APIs are external bootstrap prerequisites. Verify any GKE, logging, or registry API prerequisites against the target environment before enabling anything. This Change Set does not enable APIs or create identities. Budget, quota, image retention, log retention, and a maximum one-Job run must be approved before spending.

The intended GitHub WIF provider accepts only this exact repository, `lamanasser56/secure-financial-ai-infrastructure`, the `.github/workflows/release-google-sdp-evaluation.yml` workflow on `refs/heads/main`, and the `workflow_dispatch` event. The provider should bind immutable GitHub repository identity claims where supported; check current GitHub claim values before creating the binding. The default protected-environment gate requires independent review and restricts main. The proposed synthetic-only owner profile would use owner `lamanasser56` as the required reviewer with self-review permitted, disabled administrative bypass and main-only branch restrictions. That amendment requires explicit complete-bundle approval; independent review and separation of duties remain unproven. No environment setting has been changed. WIF additionally pins the exact approved source SHA through `approved_source_commit`. Configure the WIF provider name, release service-account email, and project ID as GitHub environment variables named `GOOGLE_SDP_RELEASE_WIF_PROVIDER`, `GOOGLE_SDP_RELEASE_SERVICE_ACCOUNT`, and `GOOGLE_SDP_RELEASE_PROJECT_ID`. They are names, not credentials. Never use JSON keys, stored OAuth tokens, or a credential file in the Docker build context.

The Terraform contract scopes `roles/artifactregistry.writer` to one repository for the release GSA and uses `roles/iam.workloadIdentityUser` only on the matching service accounts. It defines a separate runtime GSA and a custom project role containing only `serviceusage.services.use`, the documented permission for the regional content inspect and deidentify methods. This permission can cover other billable APIs enabled in the project, so the bounded endpoint and egress controls still matter. Do not grant project-wide Owner/Editor. GKE nodes need verified image-pull rights independently of the Job KSA. These are future operator actions, not implemented grants.

## Manual release and evidence

After gates 1 and 2, dispatch the workflow on main with the reviewed full commit SHA, region `us-east1`, existing immutable-tag repository name, and image name. The qualification job has no Google token permission and runs tests, lock checks, source lint, an offline deterministic image build, SBOM, Trivy, and the unchanged HIGH/CRITICAL policy. The publish job first reproduces the same image configuration ID, then uses GitHub OIDC and WIF to obtain a short-lived Google access token without writing a credential file. It checks the repository's immutable-tag setting before push. The commit-derived tag is only a staging address; the workflow records the resolved registry manifest digest and uses that digest for fresh scan, SBOM, policy, signing and verification. The local image ID and remote manifest digest are distinct identifiers; equality is not assumed. Review all uploaded evidence before accepting gate 4. A passing signature does not establish real-world detection accuracy or provenance beyond the verified workflow identity and source controls.

If registry scanning or signing fails after push, quarantine or remove the unsigned digest and its tag using a separately authorized cleanup process. Do not deploy it. Review CISA KEV and vulnerability database timestamps at release time. Retain only approved sanitized evidence for the approved retention period. No access token, OIDC token, request text, provider response text, or raw fixture output belongs in an artifact.

### Docker archive export and repaired-source gate

Both release jobs initialize an explicit `docker-container` builder with Buildx
`0.30.1` and the qualified BuildKit `0.33.1` image pinned by digest. The build
script requires `BUILDX_BUILDER`, inspects that named builder before export,
rejects other drivers and passes the name to every archive build. Builds request
no insecure entitlements. Explicit daemon flags suppress the setup action's
`security.insecure` default. Buildx `0.30.1` itself adds `network.host` for its
isolated container driver; this does not enable host networking in the Job.
Local qualification must reproduce the actual
Docker archive export, load, inspection and image configuration in two separate
builder caches, then regenerate SBOM, Trivy and policy evidence for that source.
The Dockerfile, runtime and dependencies remain unchanged by this builder repair.

The deployed WIF condition also pins the approved source commit. A repaired
commit requires a reviewed exact source-pin update before release; a builder
repair alone does not authorize changing WIF or any IAM binding. Preserve all
other trust conditions, the qualification-before-authentication order and the
image-configuration equality checks. A different configuration blocks release
pending evidence review. Never substitute a previous scan for a new build or
assume the local configuration digest equals a registry manifest digest.

### Private registry configuration lifecycle

The publish job initializes its shared `DOCKER_CONFIG` before Buildx setup.
The configuration manager accepts an absent directory or private existing
Buildx metadata, checks ownership and a `0700` root, and requires a `0600`
authentication file. It rejects symlinks, hard links, special files, unexpected
top-level entries, writable metadata, other registries and credential helpers.
It never repairs or deletes an unexpected existing directory or prints its
contents. The initial registry placeholder prevents automatic external
credential-helper selection. Login uses `--password-stdin`; checks bracket login.

The final `always()` step removes only the validated authentication file.
Buildx metadata remains available until the pinned setup action's post step
removes the builder. Its private noncredential directory remains on the
ephemeral runner until runner disposal; no recursive directory deletion is
performed. This ordering also applies after a failed push or scan. If filesystem
validation fails, stop and investigate; do not erase unexpected files blindly.

Worker qualification exercises real Docker login with dummy credentials against
an isolated loopback registry, real archive export/load and Buildx inspection,
and success/failure cleanup for both initially absent and Buildx-populated
directories. Local login demonstrates configuration handling, not Google
Artifact Registry authentication, registry publication or Cosign signing.
Those gates require fresh evidence from the single authorized manual release.

## GKE execution and containment

The existing Calico cluster remains unchanged. The proposed target is the dedicated [native evaluation cluster](../../infra/gcp/google-sdp-evaluation-cluster/README.md), with Dataplane V2, kube-dns without NodeLocal and GKE metadata at `169.254.169.254:80`. Its dedicated node GSA receives repository reader rights independently of the runtime KSA/GSA binding. No existing MASAR node identity is granted evaluation registry access.

The unapplied package is separate from `kubernetes/base`. The renderer requires project ID, the exact `google-sdp-runtime` GSA in that project and an exact `us-east1-docker.pkg.dev/...@sha256:` image reference. It writes a full eight-resource manifest, controls without a Job, a suspended live Job, separate zero-SDP network preflight and dedicated-cluster logging configuration into a temporary directory. Validate every output; rendering never applies or unsuspends anything. No Secret, extra Kubernetes RBAC, credential file, LiteLLM request or Presidio authority change is introduced.

After complete-bundle approval and signed digest verification, verify the new cluster's `networkConfig.datapathProvider`, enabled FQDN flag, installed native CRDs, kube-dns and metadata mode. Inspect all matching namespace/cluster-wide policies; NetworkPolicy and FQDNNetworkPolicy allows are additive. Apply only scoped logging and controls, then the 180-second preflight with the same qualified digest. The [probe](../../scripts/probe-google-sdp-egress.py) checks verified TLS/HTTP2 without a DLP request, metadata email without a token and unrelated/direct-IP/alternate routes. Retrieve genuine Cloud Logging verdicts and run the [evidence verifier](../../scripts/verify-google-sdp-egress-evidence.py); timeouts alone never pass. Delete the preflight Job/Pod and its ConfigMap before applying the suspended live Job, preserving one-Pod/one-Job quota. Re-read policies and unsuspend once only when every gate passes. The live path retains `--live`, the exact synthetic-only acknowledgment, fixed regional endpoint and committed corpus.

The proposed dedicated evaluation GKE cluster is in `us-east1-b`; the SDP endpoint, Artifact Registry and state bucket are in `us-east1` (South Carolina). This synthetic-text path does not establish end-to-end Saudi residency. Production residency would need separate Saudi-region compute, network, logs, storage, backup, and observability review.

Standard Kubernetes NetworkPolicy cannot enforce an FQDN destination. The revised package removes public HTTPS and uses native FQDNNetworkPolicy for DNS-derived destination IP/port enforcement. It is not Layer-7 inspection: another hostname/API sharing an allowed IP, or a direct connection to that IP, cannot be distinguished. DNS query names are not confined. This proposed network-gate clarification preserves application endpoint pinning and certificate verification; it does not establish complete regional hostname isolation, DNS exfiltration prevention or DLP-only IAM. No unrestricted fallback is permitted. Unsupported native features, successful unapproved routes or missing datapath verdicts block live execution. No customer, production, real financial or uncertain identity data may be sent.

After a separately approved bounded run, capture only schema-valid sanitized result JSON, status, timing and estimated cost. The proposed cleanup removes only evaluation resources and the new cluster/network using a saved cleanup plan, and disables its retained node identity. Retain remote states, bucket, signed immutable release/signature and final evidence; do not weaken registry immutability or disable shared APIs. Start cleanup by hour four and complete within the proposed six-hour cluster lifetime/USD 5 incremental operator stop limit. These are operator limits, not automatic billing caps. Delete temporary render/plan material after retaining sanitized summaries, and verify logs/artifacts against retention rules. Record **PASS FOR FURTHER BOUNDED INTEGRATION**, **FAIL AND RETAIN PRESIDIO**, or **INCONCLUSIVE — MORE EVIDENCE REQUIRED**. None authorizes Presidio deletion or a provider-authority change.

The reviewed seed has nine cases and 547 UTF-8 text bytes. Its call ceiling is nine inspections plus nine de-identifications, with application retries disabled, a 20-second deadline per RPC and no Job retry. A changed live corpus is rejected. The result's `provider_operations` field counts SDK invocation attempts; do not relabel those counters as server receipts or exact billed operations. Fake-client accounting is explicitly unavailable. Retain the result before the one-hour Job TTL expires and reconcile service-side request metrics where available without exposing provider responses.

The proposed profile does not close independent review, project-wide GKE workload-pool isolation, shared-IP hostname isolation, Saudi residency, production authorization or full CS6. The legacy exact namespace/KSA IAM member is project-scoped, not cluster-specific. Cloud Shell authorization and backend bootstrap must precede real plans; no plan or execution evidence is fabricated.

## Regional amendment and execution status

[ADR-005](../architecture/decisions/ADR-005-us-east1-synthetic-sdp-evaluation.md) supersedes only the historical Dammam selection. The earlier approval at `2d1c87af7e17b4c7d45591c7479d02727c75cfc5` does not authorize this region or changed image. [Read-only eligibility](google-sdp-regional-eligibility.md) records the Storage-only failure and remaining unknowns. A complete amended-source bundle needs one owner approval before backend bootstrap, IAM/API/GitHub changes, push, publication, signing, deployment or live calls.

The trusted [deployment contract](../../evaluation/google-sdp/deployment.json) selects `us-east1` and `dlp.us-east1.rep.googleapis.com`. The adapter reads only that committed artifact at startup and constructs `projects/PROJECT_ID/locations/us-east1`. No request, environment override, alternate configuration path or automatic fallback can select a location. ConfigMap, native FQDN policy, zero-call probe, Terraform, release workflow and renderer must match it. Image contents changed, so local image qualification must be regenerated before release; preserved Dammam image evidence remains historical.

At the regional-preparation checkpoint, Cloud Shell was started and
session-authorized for the failed Storage bootstrap, then its read-only environment
GET reported `SUSPENDED`. This historical observation does not establish current
authenticated availability. Credentials stayed within the native authorization
broker and were not copied to the worker. Reverify owner authentication after new
approval. Browser reauthentication and protected-release review can still require
handoffs. The historical bootstrap contract used uniform access, public-access
prevention, versioning, seven-day soft delete and noncurrent lifecycle; the diagnostic
bundle reuses the already retained bucket and both state prefixes without new
bootstrap. Save and inspect each future plan for exact resources, IAM scopes,
region and source SHA before applying that same complete binary plan. No cloud plan
is produced during preparation.

Cluster cleanup starts by hour four and must finish within six hours from creation. The operator starts it; the agent performs it only while connected. There is no automated cluster expiry or billing cap. If the session disconnects, the owner must resume or take over cleanup. Job completion TTL deletes Job objects, not clusters, disks, NAT or IPs. Stop on the USD 5 incremental operator limit and clean up on any gate failure. Retain only the documented state, disabled node identity/inactive reader grant, release/runtime identities and WIF, immutable image/signature and evidence; their storage costs continue.
