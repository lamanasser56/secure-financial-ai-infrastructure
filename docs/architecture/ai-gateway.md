# AI gateway and provider isolation

> **History.** This page describes the earlier reference design (Presidio redaction and the `kubernetes/` templates), before the GKE agent platform. It is kept as a record and is not the running platform. For the current platform see the [architecture overview](../architecture.md) and the [repository map](../REPO-MAP.md).

The approved route is trusted runtime → Presidio Analyzer → Presidio Anonymizer → LiteLLM → one approved provider. Application code must not call a provider directly or expose provider credentials. The runtime sends only validated redacted text to the gateway and accepts only structured output.

The [LiteLLM ConfigMap](https://github.com/lamanasser56/secure-financial-ai-infrastructure/blob/v2-live-evidence/kubernetes/apps/litellm/configmap.yaml) has one model alias, no fallback, no retry, bounded request limits, and a master key supplied from a Kubernetes Secret. Provider model, project and region are placeholders. The [ServiceAccount](https://github.com/lamanasser56/secure-financial-ai-infrastructure/blob/v2-live-evidence/kubernetes/apps/litellm/serviceaccount.yaml) has no cloud binding until a target environment supplies one. The gateway Service is internal; NetworkPolicy allows labeled clients only. Public HTTPS egress remains broader than a provider hostname and needs target-cluster egress enforcement.

No customer request or live provider call is qualified by this repository. See [ADR-001](decisions/ADR-001-provider-gateway.md) and the [gateway contract](../phase3/phase-3a-gateway-contract.md).
