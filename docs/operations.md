# Integration and operations

## Before deployment

1. Choose an approved provider model and region. Replace the `REPLACE_WITH_*` values in the LiteLLM ConfigMap through an environment-owned overlay or templating system.
2. Bind the gateway Kubernetes ServiceAccount to a least-privilege cloud identity in the target environment. No account address is committed here.
3. Deliver the `PORTFOLIO_LITELLM_MASTER_KEY` secret through an approved external secret mechanism. Do not add a real Kubernetes Secret manifest to Git.
4. Requalify each pinned OCI digest, vulnerability report, probe, resource limit, NetworkPolicy, DNS route, Workload Identity route, and provider egress in the actual cluster.
5. Supply application-owned authentication, tenant resolution, authorization, audit storage, and tool execution adapters. Exercise negative-path and tenant-isolation tests against those real adapters.
6. Confirm monitoring ownership, retention, alert routing, backup and restore, API audit log destination, and incident access before making a production claim.

`kubectl kustomize kubernetes/base` renders the templates for review. It does not verify CNI enforcement, cloud IAM, image safety, secret delivery, monitoring, or readiness. Applying the templates without the above integration may create nonfunctional services.

## Sensitive-data handling

Keep prompts, document content, raw provider responses, tokens, and tenant identifiers out of logs, metrics, audit-event payloads, CI artifacts, and issue reports. Use only synthetic inputs for repository qualification. Store cluster evidence in an approved location after reviewing it for internal endpoints and identifiers.
