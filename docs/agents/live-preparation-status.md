# Live-agent preparation handoff

## Current checkpoint

2026-10-04: independent local preparation completed; **live execution blocked**.
Starting source is `de4325c36bfdbb0a9522b89269affb9ea919a187`. The local commit
containing this handoff is reported separately with its exact SHA; no source push,
workflow dispatch, model request, cloud mutation or deployment follows this record.
The original MASAR repository and dirty worker checkout remain outside the edits.

| Boundary | Implemented / locally verified | Actually deployed / verified | Simulated or blocked |
| --- | --- | --- | --- |
| UI/conversations | Separate Arabic/English views, ephemeral bounded context, safe reports, clarification | Existing private worker UI responds on loopback | Demo authentication/redaction/model remain simulated |
| Shared core | TrustedRuntime and canonical registry/governance, tenant/profile binding, deterministic finance | No live agent deployment | Real identity/tenant adapters absent |
| Live protocol | Actual HTTP adapter against a loopback fixture; explicit slots, canonical tool schemas/descriptions, containment/accounting | No Vertex/Gemini request | Fixture replies/detectors prove protocol only |
| Presidio candidate | Real HTTP engines, 31 synthetic cases pass; fresh scan/SBOM | No candidate promoted/deployed | 47 HIGH findings; release prohibited |
| Reference redactor images | Exact immutable images freshly assessed | Deployment not verified here | Both committed and newer upstream images blocked |
| LiteLLM | Existing private-config template and trusted scoped-client adapter | No running/qualified gateway established | Image/evidence gates blocked; key database/scope unproven |
| Provider | Gemini through Vertex remains intended; official region/capability/IAM references reviewed | Project API already enabled by read-only inspection | Gateway identity, model entitlement and quota unproven |
| Evidence | Sanitized download contracts; HTTP attempts/response/token counters tested | No real provider receipts, measured cost or durable delivery | Offline counters are not external provider activity |

## Implemented integration preparation

The live factory now always analyzes English and Arabic, independently of browser
language. Failure of either pass blocks; no silent English-only result or fallback.
The existing validator rejects conflicting spans. This does not install detectors
or itself qualify their accuracy. See [real redactor qualification](redactor-qualification.md).

The live core binds an explicit reporting month/source from redacted text and
closed trusted selectors. Missing, ambiguous or relative months clarify before
model/tools; explicit English/Arabic date follow-ups continue with the existing
server context. It does not reuse an old month as a guessed answer. These bounded
calendar/source rules do not claim general language understanding. Questions then
reach LiteLLM unchanged except required redaction; there is no canned live answer.

Canonical tool descriptions and committed input schemas now accompany the prompt.
The Phase 3 `{summary, classification}` envelope remains; `summary` contains a
validated decision, not native SDK tool dispatch. The model proposes and the
existing governance authorizes. `out_of_scope` is a live-protocol refusal reason;
`offline_unsupported` remains the simulation's explicit limitation. The application
still offers no live-mode switch. Gemini compliance must be tested separately.

`HttpLiteLLMGateway` rejects nonapproved aliases before HTTP, fixes a 1,024 output
token request, preserves trusted startup URL/client credential and permits no
redirect, ambient proxy or retry. Provider credentials remain gateway-only.
Per-turn measurement records HTTP attempts, parsed HTTP responses and only valid
nonnegative integer token usage when every attempt returned complete usage.
Missing/malformed usage or a transport ambiguity remains unavailable. Provider
receipts and cost remain unknown; gateway replies are not proof of upstream
receipt counts. No price is inferred from arbitrary response fields. The prepared presentation distinguishes gateway HTTP attempts from simulation, shows unverified provider receipts as unavailable and never labels a gateway response as proven live-model qualification. Financial categories require an available summary first; final supporting citations must match the validated supporting sources and cannot cite the invented image fixture.

The optional sanitized measurement projection contains counters only, never raw
conversation/model/tool content. A post-model forbidden proposal correctly records
one preceding loopback HTTP response and zero tool executions. Pre-model identity,
configuration and injection denials produce zero gateway HTTP attempts. Loopback
fixtures are explicitly test doubles, not real authentication/model/detection.
Existing conversation/rate/deadline/output limits and no-retry behavior remain.

## Authentication and execution authority

The private offline UI is accessible through an owner's authenticated SSH tunnel
and worker loopback. Another process with worker access is not independently
identified by that UI. Server-selected `demo-alpha`/`demo-beta` are simulated
personas, not production login. The cookie/CSRF/handle and trusted startup tenant
binding prevent request-selected tenant/profile changes; they do not replace a
real identity issuer. The live factory continues rejecting simulated identities.

No real issuer/audience/verified subject-to-tenant capability map was provided.
This is an explicit hard gate. Do not disable that rejection or attach an operator's
broad Google credentials to an agent. A gateway principal and its keyless transport
are also not selected/verified. Existing SDP runtime/release identities and the
worker's existing identity are not authorization for this model milestone.

## Next action

First resolve the exact [redactor dependency/base blockers](redactor-qualification.md)
without a policy exception. Then qualify the gateway image/key restrictions and
an actual identity route. The [complete follow-up boundary](live-follow-up-bundle.md)
records intended resources, model/region, scenarios, budgets, costs and cleanup,
including every unresolved execution field. It is **not an executable approval
request** while these gates remain unresolved. Do not ask the owner to approve
unspecified trust, credentials or resources. Present one fully resolved bundle
only after qualification and exact identity/resource planning are complete.

Historical SDP cleanup is complete and its result was INCONCLUSIVE, not a live
model or Presidio-selection qualification. State/registry/identity retention and
prior audit UNKNOWNs remain: unavailable Data Access/state-read history, unscanned
historical state versions, incomplete historical IAM deltas, impersonation/signed
URL/worker credential assessment, independent review and network Layer-7/shared-IP/
DNS-query containment. This milestone resolves none of those audit findings.
