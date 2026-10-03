# Google SDP native synthetic evaluation package

This **unapplied, evaluation-only** package belongs to the [proposed complete execution bundle](../../../docs/security/google-sdp-synthetic-execution-proposal.md). Presidio remains authoritative. No real data or provider cutover is authorized. Templates contain placeholders and are not deployable until a trusted operator renders a verified signed digest. The package is absent from the production base. No Secret, credential file or Kubernetes RBAC grant is included.

## Target and boundary

The proposed [dedicated cluster](../../../infra/gcp/google-sdp-evaluation-cluster/README.md) uses Dataplane V2 and native FQDNNetworkPolicy, standard kube-dns without NodeLocal and GKE metadata mode. The existing Calico/MASAR cluster is unchanged and cannot accept this native package. Verify the feature flag, CRDs, DNS path and actual metadata behavior before applying anything. No custom CRD is installed as a workaround and no public HTTPS fallback is allowed.

The namespace and KSA are both `google-sdp-evaluation`; the namespace enforces restricted Pod Security. NetworkPolicy denies all ingress and permits only cluster kube-dns TCP/UDP 53 and Dataplane V2 metadata `169.254.169.254:80`. Native FQDNNetworkPolicy permits only the fixed `dlp.us-east1.rep.googleapis.com` destination on TCP 443. Both policies select every Pod. Standard NetworkPolicy cannot enforce an FQDN. The native allow is DNS-derived IP/port enforcement, **not Layer-7 hostname inspection**: another hostname/API sharing an allowed IP, or direct use of that IP, cannot be distinguished. DNS query names are not confined. Matching policies are additive, so a broad NetworkPolicy could bypass the boundary. Inspect all namespace and cluster-wide policies before preflight and before unsuspending the live Job. Application endpoint pinning and TLS hostname verification remain mandatory.

The dedicated KSA opts into token automount for this bounded GKE Workload Identity path; no Kubernetes API permission is granted. Its GSA annotation is inserted only during trusted rendering. The exact namespace/KSA IAM member is project-scoped and does not encode a cluster; equally named KSAs in another project cluster remain a production isolation limitation. No matching KSA is created on the existing cluster. Kubelet image pulls use the new node GSA's repository reader grant, independently of runtime Workload Identity.

## Rendering and ordered execution

```text
bash scripts/render-google-sdp-evaluation-job.sh PROJECT_ID google-sdp-runtime@PROJECT_ID.iam.gserviceaccount.com us-east1-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST
bash scripts/validate-google-sdp-deployment.sh /tmp/portfolio-google-sdp-render.XXXXXXXX/google-sdp-evaluation.yaml
bash scripts/render-google-sdp-evaluation-job.sh --cleanup /tmp/portfolio-google-sdp-render.XXXXXXXX
```

Rendering never applies or unsuspends resources. It requires the exact runtime GSA in the image's project, rejects tags/non-Artifact-Registry images and writes only a renderer-owned temporary directory. Output files separate the eight-resource full manifest, seven controls without a Job, one suspended live Job, two-resource preflight and new-cluster logging configuration. All outputs are validated; committed templates are never edited. Retain signed digest and rendered source hashes in private evidence, then clean up the temporary directory.

After approval and release verification, configure only the new cluster's existing `NetworkLogging/default` object using the supplied logging configuration. Delegated allow logging selects annotated evaluation policies; delegated deny logging selects the annotated evaluation namespace. Apply controls, then one preflight Job/immutable ConfigMap. The reviewed [probe source](../../../scripts/probe-google-sdp-egress.py) mounts read-only and uses the **same qualified image digest**, with no extra tools or image. It checks metadata email without a token, TLS certificate/HTTP2 reachability without a DLP request, an unrelated DNS destination/direct IP, alternate HTTPS and alternate DNS. It has a 180-second deadline, 600-second TTL, zero backoff and bounded connection timeouts. Its only output is sanitized connection evidence and explicit limitations.

A timeout alone is not enforcement proof. Retrieve genuine GKE `policy-action` logs for that Pod/time window and require matching allow/deny verdicts with the [offline verifier](../../../scripts/verify-google-sdp-egress-evidence.py). Missing logs, refused/reset connections, overlapping allowed/negative IPs or any unapproved successful route block execution. Do not manufacture evidence or broaden policy to recover from failure. Delete the preflight Job/Pod and its ConfigMap before creating the suspended live Job; the quota remains **one Pod and one Job**. Re-read policies and unsuspend the live Job exactly once only when every release, identity, network and evidence gate passes. The [runbook](../../../docs/security/google-sdp-live-runbook.md) controls execution and cleanup.

## Bounded live Job

The live Job has zero retries, a 900-second active deadline, 3600-second completion TTL, CPU/memory/ephemeral-storage requests of 100m/128Mi/64Mi and limits of 500m/512Mi/256Mi. UID/GID 65532, non-root execution, RuntimeDefault seccomp, dropped capabilities, no privilege escalation, read-only root and no exposed ports/host privileges are explicit. It uses the committed corpus only, `--live` and the exact synthetic-only acknowledgment. At most nine inspect and nine deidentify SDK attempts use 20-second deadlines; no application retry, second live Job, global endpoint, cross-region fallback or LiteLLM path is introduced. Only schema-valid sanitized result JSON reaches stdout.

Retain evidence before TTL, then remove evaluation resources and apply the reviewed dedicated-cluster cleanup plan. Preserve remote states, bucket, immutable signed release/signature and final sanitized evidence. No indefinitely running cluster is authorized. The proposed owner-review amendment is pending, is not independent review and grants no production or real-data authority.
