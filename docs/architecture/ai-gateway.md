# AI gateway and provider isolation

The approved route is trusted runtime → Presidio Analyzer → Presidio Anonymizer → LiteLLM → one approved provider. Application code must not call a provider directly or expose provider credentials. The runtime sends only validated redacted text to the gateway and accepts only structured output.

The [LiteLLM ConfigMap](../../kubernetes/apps/litellm/configmap.yaml) has one model alias, no fallback, no retry, bounded request limits, and a master key supplied from a Kubernetes Secret. Provider model, project and region are placeholders. The [ServiceAccount](../../kubernetes/apps/litellm/serviceaccount.yaml) has no cloud binding until a target environment supplies one. The gateway Service is internal; NetworkPolicy allows labeled clients only. Public HTTPS egress remains broader than a provider hostname and needs target-cluster egress enforcement.

No customer request or live provider call is qualified by this repository. See [ADR-001](decisions/ADR-001-provider-gateway.md) and the [gateway contract](../phase3/phase-3a-gateway-contract.md).
