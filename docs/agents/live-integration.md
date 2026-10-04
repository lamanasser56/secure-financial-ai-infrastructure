# Live agent integration prerequisites

## Current gate

The entry points are offline-only. Do not set credentials to turn them into a live service. `prepare_gateway_core` prepares a reusable composition for a separately authorized integration; no live provider call, IAM change, API enablement, deployment or model release is part of this implementation.

## Exact prerequisites

1. Supply tested application-owned `Authenticator`, `TenantResolver` and `Authorizer` implementations. Preserve trusted tenant context and the keyed pseudonymous-reference invariant. Qualify both agent actions against real user capabilities. Simulated demo identities are rejected by the live factory.
2. Qualify real Presidio Analyzer and Anonymizer startup URLs, connectivity, timeouts and detector coverage, including Arabic inputs and incomplete/unavailable redaction. Failed redaction must block the model path. No SDP fallback or automatic cutover exists.
3. Deploy/qualify the existing LiteLLM gateway boundary separately. Keep `secure-financial-chat` as the agent alias. Select an approved, supported Gemini model and provider processing location in trusted gateway configuration. The existing [gateway template](../../kubernetes/apps/litellm/configmap.yaml) uses the `vertex_ai/` route and placeholders; it is not deployable as-is. LiteLLM documents that route for Gemini via Vertex AI. No direct provider SDK belongs in either agent. [Official provider documentation](https://docs.litellm.ai/docs/providers/vertex).
4. Set the gateway's own Google identity and minimum model-access permissions through a separately reviewed deployment. Google documents ADC and workload identity authentication for that boundary. Do not place JSON service-account keys or provider credentials in the agent, UI, source or report. Existing SDP identities and approvals do not authorize Vertex model use. [Official authentication documentation](https://docs.cloud.google.com/vertex-ai/docs/authentication).
5. Provide the trusted startup LiteLLM URL and a separate model-scoped virtual client key through `PORTFOLIO_LITELLM_CLIENT_KEY`. Never use `PORTFOLIO_LITELLM_MASTER_KEY` as an agent credential. Qualify model restrictions, spend/rate limits, expiry and revocation at the gateway; do not assume an opaque key has those properties. Browser/request fields cannot select the URL, alias or key. [Official virtual-key documentation](https://docs.litellm.ai/docs/proxy/virtual_keys).
6. The live factory now requires both English and Arabic Presidio passes on every text. Real detector/image qualification remains blocked; see [redactor qualification](redactor-qualification.md). Explicit date/source slots, clarification continuation, canonical descriptions/schema hints and bounded gateway accounting are locally prepared. The UI is still offline-only. Retain the existing Phase 3 output envelope. Qualify the model's JSON-encoded decision inside `summary` against the new closed schema, including malformed proposals and output injection. Tool results, retrieved documents and model text remain untrusted.
7. Qualify durable sanitized audit delivery, real identity isolation, provider errors/deadlines, gateway egress and appropriate deployment authentication/network controls. Run a separately approved synthetic qualification with explicit cost/request limits before any broader use.

No model version, regional availability, IAM role grant, deployment endpoint or live-key scope is invented by this change. Provider/model location must be selected and verified by a trusted operator; there is no request-selected region, automatic provider fallback or Saudi-residency claim. Cost per real run remains unknown until the model and gateway budget are qualified.

## Unresolved blockers

Real identity adapters, real Presidio/language qualification, approved Gemini model/processing region, gateway/provider workload identity, scoped client-key evidence, durable audit persistence and production deployment controls are not supplied by these demonstrations. The private UI is not authorized for public exposure. None of its simulated output proves live Gemini behavior, SDP accuracy, production readiness or full CS6 completion.

The [single follow-up bundle](live-follow-up-bundle.md) records the actual adapter protocol, mandatory English/Arabic Presidio passes, proposed private services, identity/key gates, cloud deltas that require exact review, synthetic operation/cost ceilings and cleanup. Arabic interface support does not itself qualify detector coverage or remove any of these blockers. Current CLI/UI remain offline-only.

The current [preparation handoff](live-preparation-status.md) records the actual local qualification and precise blocked gates. Do not execute the proposed bundle until its image, identity and resource gates are resolved.
