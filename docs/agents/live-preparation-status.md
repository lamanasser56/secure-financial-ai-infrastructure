# Live-agent preparation handoff

## Current checkpoint

The current [context-pattern preparation](../security/google-sdp-context-policy.md)
adds a separate 86-case synthetic policy and proposed SDP-only execution bundle.
The [new ADR](../architecture/decisions/ADR-007-context-pattern-redaction-candidate.md)
records its accepted offline scope, including bounded canonical label/variant
coverage; `العوية` is one regression case. No live execution or authority selection
occurred. Independent key-to-HTTP binding and operator-only subject revocation are
prepared locally; actual proxy database/key and real issuer gates stay unresolved.
The validation counts below belong to the preceding checkpoint; current worker
totals and exact source are in the new owner handoff. UI assets remain unchanged.

The [independent identity/gateway candidates](identity-and-gateway-preparation.md)
and [bounded research decision](../security/google-sdp-provenance-decision.md)
advance the current checkpoint without replacing the running offline UI. JWT
signature verification/server grants and scoped-key contracts are locally prepared;
actual issuer, key/database enforcement and qualified deployment remain gates.
The [proposed ADR](../architecture/decisions/ADR-006-redaction-qualification-scope.md)
requires an explicit scope decision; full 87-case replacement remains blocked.

Fresh worker validation for this checkpoint: **476 tests, 473 PASS, three skips**
(opt-in PostgreSQL RLS and two optional SDK-shape tests in the main environment).
Separate locked-SDK gates pass all 34 adapter/robustness and three email-candidate
tests without skips. All six locks, source/schema/YAML, 307 links/81 references,
74 Markdown/48 YAML/four workflows/20 shell lint and repository secret scans pass.
The existing 91 browser checks are retained evidence; UI assets were not changed.
Final gateway archives/configuration reproduce; fresh policy has zero HIGH/CRITICAL,
16 MEDIUM/eight LOW and 1,687 SBOM components. Actual isolated proxy health passes;
HTTP 400 from the unissued marker does not prove scoped-key authentication denial.
Virtual-key/database and full gateway protocol gates remain unqualified.

2026-10-04: independent local preparation completed; **live execution blocked**.
Starting source for this checkpoint is `02ebb0443675b62aee494c3194905d25146d5d4f`;
the retained conversation UI source is `de4325c36bfdbb0a9522b89269affb9ea919a187`. The local commit
containing this handoff is reported separately with its exact SHA; no source push,
workflow dispatch, model request, cloud mutation or deployment follows this record.
The original MASAR repository and dirty worker checkout remain outside the edits.

| Boundary | Implemented / locally verified | Actually deployed / verified | Simulated or blocked |
| --- | --- | --- | --- |
| UI/conversations | Separate Arabic/English views, ephemeral bounded context, safe reports, clarification | Existing private worker UI responds on loopback | Demo authentication/redaction/model remain simulated |
| Shared core | TrustedRuntime and canonical registry/governance, tenant/profile binding, deterministic finance; unwired JWT/server-grant candidate | No live agent deployment | Actual issuer/key snapshot/grants and production transport absent |
| Live protocol | Actual HTTP adapter against a loopback fixture; explicit slots, canonical tool schemas/descriptions, containment/accounting | No Vertex/Gemini request | Fixture replies/detectors prove protocol only |
| Presidio candidate | Real HTTP engines, 31 synthetic cases pass; fresh scan/SBOM | No candidate promoted/deployed | 47 HIGH findings; release prohibited |
| Reference redactor images | Exact immutable images freshly assessed | Deployment not verified here | Both committed and newer upstream images blocked |
| LiteLLM | Unpromoted candidate image policy/reproducibility pass; trusted scoped-client adapter | No running/qualified gateway established | Registry provenance, key database/scope and actual proxy tool protocol unproven |
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

No actual issuer/audience/public-key snapshot/subject grant set was provided.
The candidate adapter now implements signature validation and server mapping at
the existing seams, with local RSA/HTTP-stub tests. It is not selected by the UI
and local signing does not establish a real owner login or issuer lifecycle.
This is an explicit hard gate. Do not disable that rejection or attach an operator's
broad Google credentials to an agent. A gateway principal and its keyless transport
are also not selected/verified. Existing SDP runtime/release identities and the
worker's existing identity are not authorization for this model milestone.

## Next action

Bounded SDP preparation now has [safe partial fixtures and exact blocked classes](../security/google-sdp-agent-coverage.md),
offline robustness/deadline/accounting tests and a
[fresh candidate checkpoint](../security/google-sdp-agent-preparation-checkpoint.md).
The full 87-case campaign is blocked on five required provenance/format/configuration
sets; no easier campaign replaces it. The completed bounded research pass yields
per-class unresolved decisions and a concrete proposed scope choice. Independent
gateway/identity candidate work proceeds without promotion; Google precision/recall,
live-agent model/authentication and authority selection remain unproven.

2026-10-04 owner steering: **stop further Presidio remediation**. Preserve its
source, 31 passing local detector cases, blocked image/SBOM/scan evidence and all
completed agent changes. No replacement image is promoted; Presidio remains
authoritative. SDP replacement evaluation is the intended direction; follow the
[bounded qualification and conditional retirement plan](../security/google-sdp-agent-qualification-plan.md).

Qualify all required classes and privacy/runtime/operational gates before a separate
provider-selection ADR. Gateway/key restrictions, real identity, durable audit and
model qualification remain independent blockers. The
[follow-up boundary](live-follow-up-bundle.md) preserves their preparation; its
Presidio remediation path is paused. This is **not an executable approval request**.
No new live call, cloud change or cutover is authorized here. Present one resolved
bundle after exact qualification, identities, resources, budgets and cleanup are ready.

Historical SDP cleanup is complete and its result was INCONCLUSIVE, not a live
model or Presidio-selection qualification. State/registry/identity retention and
prior audit UNKNOWNs remain: unavailable Data Access/state-read history, unscanned
historical state versions, incomplete historical IAM deltas, impersonation/signed
URL/worker credential assessment, independent review and network Layer-7/shared-IP/
DNS-query containment. This milestone resolves none of those audit findings.
