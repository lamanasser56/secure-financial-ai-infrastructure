# Integrated Google SDP milestone readiness

Stage 1 prepares a single reviewed bundle for a signed registry release and one bounded synthetic evaluation. No cloud provisioning, GitHub setting, release run, registry publication, signing, Kubernetes apply or Google SDP request is authorized until that bundle is explicitly approved. Presidio remains authoritative regardless of the evaluation outcome.

## Read-only inventory

The approved starting commit was verified after fetching origin. The project is active with billing available. Artifact Registry, IAM, IAM Credentials, GKE and Storage APIs are enabled; DLP, STS and Resource Manager API enablement remain execution prerequisites. No state bucket, Artifact Registry repository, dedicated release WIF provider, evaluation GSA or GitHub release environment was found. There are no previous manual SDP release runs.

The existing GKE cluster uses Calico NetworkPolicy, NodeLocal DNSCache and GKE metadata mode. Its default node identity has a storage-read access scope but no project-level registry reader grant was found. The evaluation namespace does not exist. No existing FQDN-capable egress gateway or proxy was identified. The available Cloud Shell environment is suspended; its authenticated operator session must be activated and authorized before Terraform execution. No credentials may be copied to the build worker.

The current GitHub repository has only its owner as a collaborator. The runbook's independent environment-review requirement therefore needs an explicitly designated trusted reviewer; self-approval must not be presented as independent review. These identity and egress prerequisites remain open, not waived.

## Four identity boundaries

| Boundary | Permission and resource scope |
| --- | --- |
| Operator | Use the existing authenticated operator in Cloud Shell for approved provisioning and Kubernetes operations. Do not add a broad IAM grant or export its credentials to the worker. |
| GitHub release | Dedicated release GSA with writer rights on one evaluation repository; exact numeric repository and owner IDs, main branch, dispatch event, release workflow and protected environment subject. |
| GKE node pull | Existing node GSA with reader rights only on the evaluation repository and an independently verified storage-read scope. Pod Workload Identity does not authorize kubelet pulls. |
| Evaluation Pod | Dedicated `google-sdp-evaluation` namespace/KSA, runtime GSA impersonation, and the one-permission content-call custom role. No registry role or Kubernetes RBAC grant. |

The regional inspect and deidentify methods both document `serviceusage.services.use` on the parent resource. This permission also permits consumption of other enabled services; it is not an IAM-level restriction to DLP. Endpoint pinning and the independently reviewed egress boundary remain necessary. State-backed Terraform must use the committed provider lock. With no backend bucket, Stage 1 cannot produce a complete backend-backed saved plan.

## Bounded execution proposal contract

Worker qualification refreshed the changed image's SBOM and Trivy evidence with zero HIGH or CRITICAL findings and the unchanged zero-exception policy evaluator. A fresh uncached build matched the actual configuration digest. The release workflow now reads configuration bytes from Docker archives, avoiding Docker image-store differences in `.Id`; it independently resolves the pushed registry manifest digest before signing. No signed release exists yet.

Before the first persistent mutation, record the exact project, project number, backend bucket/location/configuration, GitHub numeric identities and reviewer, resource names, API enablements, IAM members and scopes, registry URL, source commit, egress mechanism, execution environment, cost limits and cleanup. Keep environment-specific values, state and binary plans outside Git. A state bucket must have uniform access, enforced public-access prevention and versioning; do not apply a locked retention policy that prevents Terraform lock-object deletion.

After approval, initialize the approved backend, inspect a saved plan and apply only the reviewed resource set. Stop on an unexpected deletion, replacement or broader permission. Configure only the approved environment and non-secret variables, fast-forward reviewed source, dispatch once, and require digest-linked scans, SBOM, policy and exact-identity Cosign verification before rendering the Job. A push also triggers existing CI; it is not a manual release retry. Each release job is bounded to 45 minutes and rejects workflow rerun attempts.

The committed corpus contains nine cases and 547 UTF-8 text bytes: four required email detections, two negative controls and three observation-only cases. A live harness rejects a supplied corpus that differs from the committed seed. It makes at most nine inspection and nine de-identification invocations, with no application retries and a 20-second deadline for each RPC. Sanitized evidence reports SDK invocation attempts, which do not by themselves prove server receipts or billing. Fake transports report their accounting as unavailable, never as real Google requests.

The evaluation Job has no retry, a 900-second active deadline and a 3600-second completion TTL. The Pod requests 100m CPU, 128Mi memory and 64Mi temporary storage; limits are 500m CPU, 512Mi memory and 256Mi temporary storage. It uses UID/GID 65532, restricted Pod Security, a read-only root filesystem, dropped capabilities, no privilege escalation and RuntimeDefault seccomp. No existing MASAR workload, cluster sizing, LiteLLM path, tenant, database or runtime redactor authority changes.

The package permits NodeLocal DNS at `169.254.20.10:53` and documented GKE metadata variants. Standard NetworkPolicy still permits public HTTPS and cannot enforce the regional FQDN. Do not apply or run the live Job until a separately reviewed FQDN-capable control or equivalent target enforcement is available. Application pinning alone does not meet the stronger runbook gate.

## Evidence, cleanup and outcome

Collect only sanitized result JSON, workflow URL, exact registry digest, Cosign verification, scan/SBOM/policy evidence, tool versions and a reviewed plan summary. Download workflow artifacts before their 14-day expiration; retain final evidence in a private approved workspace. Never commit credentials, state, binary plans, tokens, fixture echoes or raw provider responses. Keep final remote state and evidence; remove temporary render directories, the evaluation Job/Pod and evaluation namespace only under the approved cleanup scope.

The final signed release and immutable tags can continue to incur registry storage costs. State versions and existing worker/cluster resources also remain cost-bearing. Account for inter-region image transfer and logs. Bounded call counts and deadlines are execution limits, not a billing cap; use the approved incremental spending limit and do not silently add a recurring proxy or other infrastructure.

Report connectivity, signed publication, hardened execution, required-detection failures, false positives, operations and security gates separately. Observation-only cases keep the harness outcome inconclusive when no required case fails. The corpus does not prove Saudi identifiers, financial identifiers, phone/card accuracy, Arabic, images or OCR. Only the existing outcomes in the [evaluation plan](google-sdp-evaluation-plan.md) may be used. Any authority change requires its own reviewed architectural decision.
