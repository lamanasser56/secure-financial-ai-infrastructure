# Google SDP synthetic evaluation Job

This is an **unapplied, evaluation-only** Kustomize package. It is deliberately absent from the production base. Presidio remains authoritative. The committed templates contain placeholders and are not deployable until a trusted operator renders and reviews them. No Secret, Kubernetes RBAC grant, or Google credential is included.

The dedicated `google-sdp-evaluation` namespace enforces the restricted Pod Security Standard. The Job has one Pod, no retries, a 15-minute active deadline, one-hour cleanup TTL, fixed CPU, memory and ephemeral-storage requests and limits, and no writable container filesystem. Its image must be a `me-central2-docker.pkg.dev` digest from the same project as the bound Google service account. It runs the image's existing synthetic corpus with `--live` and the exact synthetic-only acknowledgment. Only the runner's sanitized JSON result is written to stdout; retain and review logs under a separately approved evidence policy.

The dedicated Kubernetes ServiceAccount opts into token automount for this bounded GKE Workload Identity use. The projected service-account identity is used by the GKE metadata server path; no Kubernetes API permission is granted. Confirm the actual token and metadata behavior on the target GKE dataplane before deployment. The GSA annotation is inserted only during temporary rendering. The target administrator must create the external GSA, bind the exact KSA principal, enable required APIs, and grant narrowly scoped IAM rights in a later authorized change.

Render after separate approval, with synthetic placeholders replaced by operator supplied, validated non-secret identity names and a verified signed digest:

```text
bash scripts/render-google-sdp-evaluation-job.sh PROJECT_ID GSA_EMAIL me-central2-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST
bash scripts/validate-google-sdp-deployment.sh /tmp/portfolio-google-sdp-render.XXXXXXXX/google-sdp-evaluation.yaml
bash scripts/render-google-sdp-evaluation-job.sh --cleanup /tmp/portfolio-google-sdp-render.XXXXXXXX
```

Rendering never applies the Job. The output is temporary and should be deleted after review. The fixed application endpoint is `dlp.me-central2.rep.googleapis.com`. Standard Kubernetes NetworkPolicy cannot enforce an FQDN destination. This policy denies ingress, permits cluster DNS and scoped GKE metadata endpoints, and permits public TCP 443 except private and link-local ranges. That last rule is broader than the regional API hostname; verify cluster DNS, dataplane, egress routing and an external FQDN-capable egress control before any live run. Do not claim network-level regional containment from this manifest alone.
