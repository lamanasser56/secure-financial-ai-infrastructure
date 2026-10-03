# Bounded live-agent qualification follow-up bundle

## Status and scope

Prepared, not executed. The present UI/CLI are offline-only. Their text boxes and Arabic translations do not establish live agent capability. Preserve Presidio authority, separate read-only tool profiles, synthetic tenants, private loopback/SSH access, exact source/schema confinement, bounded context and no retries. No existing SDP publication/evaluation approval authorizes Vertex model calls, new identity bindings, billing or new services for this bundle.

One follow-up should prepare and qualify the complete boundary below before a single concrete execution checkpoint. Do not split it into implicit permissions for individual services. There is no live enablement switch in the current UI.

## Existing adapter inspection

The [LiteLLM adapter](../../runtime/phase3/adapters.py) posts to trusted startup `/chat/completions` with alias `secure-financial-chat`, `PORTFOLIO_LITELLM_CLIENT_KEY`, `response_format=json_object`, the closed `{summary, classification}` envelope and pseudonymous tenant/correlation metadata. It does not send native provider function declarations, parse native `tool_calls`, report usage/prices or permit redirect/proxy routing. The agent instead parses a closed JSON decision inside `summary`; this protocol must be qualified with the actual model. Application governance, not a provider SDK, executes tools.

The prompt now carries the actual redacted question, language, untrusted redacted history, profile allowlist, bounded arguments and validated observations. A real model still needs qualified tool purpose/schema descriptions and examples of this nested decision envelope. Unknown proposals must fail, never fall back to canned results. The current live prototype asks for an explicit source/month before dispatch; the offline grammar must not masquerade as a real model interpreter. Qualify trusted continuation and model-proposed clarification/extraction separately before wiring it to the conversation server.

`prepare_gateway_core` rejects simulated identities, synthetic redaction service doubles and a client key equal to a supplied master key. It currently constructs `HttpPresidioAnalyzer` with its default `language="en"`. **This does not qualify Arabic or mixed-language input/output.** Presidio defaults to English models/recognizers; other languages require configured NLP and language-specific recognizers. Qualify a trusted server-selected multi-language strategy for input, tool output, history and final answers; do not let browser language disable detectors. [Official Presidio language configuration](https://github.com/microsoft/presidio/blob/main/docs/analyzer/languages.md).

## Proposed local services and trusted configuration

| Boundary | Concrete proposed contract | Qualification required |
| --- | --- | --- |
| Agent application | Existing worker, private `127.0.0.1:8765`, SSH access, same two profiles | Real authenticator/resolver/authorizer, issuer/audience/signature/expiry validation; trusted tenant map; per-identity quotas independent of reset |
| LiteLLM gateway | Private `127.0.0.1:4000`, only alias `secure-financial-chat`, Gemini via `vertex_ai/` | Pinned qualified release/image; actual structured decision compliance; no retry/fallback; approved model/location and provider request bounds |
| Presidio Analyzer / Anonymizer | Private `127.0.0.1:5001` / `127.0.0.1:5002` | Pinned images/NLP artifacts; English/Arabic/mixed-language synthetic detection tests; outage/malformed/incomplete result blocks every model stage |
| Gateway key database | Private PostgreSQL on `127.0.0.1:15432`, dedicated gateway-key database | Existing approved database reuse only if isolation/ownership permits; otherwise reviewed ephemeral local instance, separate role, private temporary volume and deletion |
| Application key | Separate virtual key per profile, only `/chat/completions` and approved alias | Short expiry, no administrative ownership/routes, model/rate/spend restrictions verified by real deny tests; stored only in private startup secret handling |
| Audit sink | Bounded local private sanitized-event destination | No prompts, question/history, tokens or credential material; durable failure handling and explicit retention/deletion proof |

The [LiteLLM virtual-key documentation](https://docs.litellm.ai/docs/proxy/virtual_keys) requires PostgreSQL and describes model access, key expiry and budget/rate controls. Key-management administrative credentials remain gateway/operator-only; neither browser nor agents receive them. Opaque-key inequality alone is insufficient. No source/report embeds credentials or database URLs with passwords.

Keep gateway URL, alias, client key and provider configuration trusted at startup. Gateway-owned ADC/workload identity handles Google access; agents have no Google SDK or provider credentials. The documented `vertex_ai/` route supports the intended gateway boundary. [Official LiteLLM Vertex documentation](https://docs.litellm.ai/docs/providers/vertex), [Google authentication](https://docs.cloud.google.com/vertex-ai/docs/authentication).

## Cloud and identity delta: hard prerequisites, no authorized mutation

The execution checkpoint must name a verified project, exact supported model, processing region, gateway principal and complete IAM plan. These are currently **unselected/unverified**; never derive them from browser text, the SDP GSA or an old evaluation approval. No regional fallback or Saudi-residency claim is proposed.

Read-only project/API/model/region/organization-policy eligibility assessment comes first. If new cloud access is needed, the one reviewed plan must enumerate only the required model API (`aiplatform.googleapis.com`), gateway identity and proven prediction permissions/bindings for that selected project. The official prediction RPC lists `aiplatform.endpoints.predict`; this is a candidate permission to verify against the selected operation and custom-role support, not an invented role or applied grant. Existing SDP release/runtime/node identities and their IAM/WIF restrictions remain unchanged. [Official prediction API permission reference](https://docs.cloud.google.com/vertex-ai/docs/reference/rpc/google.cloud.aiplatform.v1).

No cluster, registry, image release, public listener, firewall change, billing change, storage bucket or new GCP service account is presumed necessary for a loopback worker qualification. If the verified identity route requires one, enumerate its exact scope/retention in the saved-plan review at that single checkpoint. Do not execute an unspecified alternative. A real application identity issuer/audience and tenant-capability mapping are also blockers; the existing demo cookie is simulated authentication, not a substitute.

## Qualification and bounded execution proposal

1. Implement and test real identity adapters and bilingual fail-closed redaction locally on the worker, then qualify the exact LiteLLM gateway build and scoped-key restrictions with a local fake upstream. No external model request at this stage.
2. Prepare exact private service/image/NLP versions, issuer/audience, startup addresses, selected cloud model/project/location, necessary IAM/API diff, cost estimate and cleanup commands. Scan source/history/evidence; render no secret into reports. Stop if any value or required grant remains unknown.
3. Present one saved-plan/service launch and synthetic live-test bundle for owner review. Proposed live ceiling: eight committed synthetic turns total across both profiles/languages, at most 32 external model attempts, at most 32 read-only tool attempts, no retries, one-hour service lifetime and a USD 1 operator stop threshold. These are proposals, not inherited approval or guaranteed billing caps. Gateway-side expiry/rate/spend and input/output token bounds must be proven; billed cost/token usage remain unavailable until authenticated evidence exists.
4. Reverify exact identity, real Presidio and scoped client key, then run only the approved synthetic cases once. Prove clarification without premature finance access, unavailable data, tenant/profile/context denial, endpoint/key override rejection, genuine tool selection, evidence-grounded explanation and Arabic/English output. Failed required controls stop the run.
5. Revoke qualification client keys, stop temporary local services, remove their private volumes/credentials, return any explicitly temporary IAM grant to the reviewed prior state and verify cleanup. Retain sanitized event/qualification summaries only for the owner-selected retention; never retain transcripts or tokens. No production rollout or broader data access follows automatically.

## Remaining blockers

Real identity/tenant adapters, bilingual Presidio detector qualification, actual gateway/key database, verified scoped keys, exact Gemini model/processing location/Google identity, structured-proposal compliance, durable audit, live token/cost evidence and independent network enforcement remain unproven. The separate SDP evaluation was inconclusive and supplies no replacement-redactor or live-model authorization. This proposal changes no running cloud resource and requests no unspecified execution approval.
