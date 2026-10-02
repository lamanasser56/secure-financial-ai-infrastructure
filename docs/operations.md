# Integration and operations

## Before deployment

1. Choose an approved provider model and region. Replace the `REPLACE_WITH_*` values in the LiteLLM ConfigMap through an environment-owned overlay or templating system.
2. Bind the gateway Kubernetes ServiceAccount to a least-privilege cloud identity in the target environment. No account address is committed here.
3. Deliver the server-administrative `PORTFOLIO_LITELLM_MASTER_KEY` only to LiteLLM through an approved external secret mechanism. The [non-deployable example](../kubernetes/secret-templates/litellm-master-key.secret.example.yaml) documents its key; never put a real value in Git or include this example in Kustomize.
4. Provision a separate scoped LiteLLM client key for `secure-financial-chat` with appropriate budget and rate limits. Deliver it to the trusted runtime as `PORTFOLIO_LITELLM_CLIENT_KEY`, independently rotatable and revocable. Set `PORTFOLIO_LITELLM_BASE_URL` from trusted deployment configuration to the internal LiteLLM service. No runtime workload receives the administrative key; no request may select the endpoint. This repository does not provision or rotate live keys and has no runtime Deployment example.
5. Requalify each pinned OCI digest, vulnerability report, probe, resource limit, NetworkPolicy, DNS route, Workload Identity route, and provider egress in the actual cluster.
6. Supply application-owned authentication, tenant resolution, authorization, audit storage, and tool execution adapters. Exercise negative-path and tenant-isolation tests against those real adapters.
7. Confirm monitoring ownership, retention, alert routing, backup and restore, API audit log destination, and incident access before making a production claim.

`kubectl kustomize kubernetes/base` renders the templates for review. It does not verify CNI enforcement, cloud IAM, image safety, secret delivery, monitoring, or readiness. Applying the templates without the above integration may create nonfunctional services.

## Sensitive-data handling

Keep prompts, document content, raw provider responses, tokens, and tenant identifiers out of logs, metrics, audit-event payloads, CI artifacts, and issue reports. Use only synthetic inputs for repository qualification. Store cluster evidence in an approved location after reviewing it for internal endpoints and identifiers.
