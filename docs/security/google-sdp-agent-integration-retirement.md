# Conditional SDP integration and Presidio retirement

**Preparation only, 2026-10-04.** Runtime authority, manifests, locks, gateway
configuration and historical evidence remain unchanged. Further Presidio remediation
is stopped. The [coverage decision](google-sdp-agent-coverage.md) blocks the full SDP
campaign. No authority change follows from passing adapter tests or an image scan.

## Consumer inventory from current source

| Consumer / contract | Exact active paths | Conditional migration work |
| --- | --- | --- |
| Neutral redactor plus provider-specific stage/error labels | `runtime/phase3/trusted_runtime.py`, `contracts/phase3/sanitized-trace-envelope.schema.json` | Preserve `RedactorClient`, `RedactionResult`, all eight categories and pseudonymous tenant references. After an ADR, version honest provider-neutral audit stages/errors rather than reporting SDP as Presidio. Fail closed before gateway activity. |
| Current HTTP construction and validators | `runtime/phase3/adapters.py` | Keep gateway separation, URL/credential/alias restrictions, bounded transport and validated output. Retire only obsolete Presidio HTTP adapters after all consumers migrate. |
| Agent factory / core / UI projections | `runtime/agents/demo.py`, `runtime/agents/core.py`, `runtime/agents/presentation.py` | Current live composition still constructs bilingual Presidio; offline composition remains labelled simulated. Later inject one qualified redactor at trusted startup, update authority labels, never add a browser provider selector. |
| Invocation and policy | `runtime/phase4/tool_invocation.py`, `runtime/agents/controls.py`, `contracts/agents/tool-registry.json` | Retain authoritative registry, per-profile capabilities, tenant binding, result minimization and prompt-injection assessment. No parallel policy engine. Review every sanitization consumer. |
| Kubernetes example services and egress | `kubernetes/apps/presidio/`, `kubernetes/base/kustomization.yaml` | Later inventory deployed consumers, remove unused services/ServiceAccounts/config/egress only through a reviewed change. Do not remove Presidio or widen egress now. |
| Evaluation authority guards | `scripts/validate-google-sdp-deployment.sh`, `scripts/validate-google-sdp-execution.py`, `scripts/evaluate-google-sdp.py`, `kubernetes/apps/google-sdp-evaluation/` | Keep synthetic-only evaluation separate from runtime. A new campaign needs its own exact corpus/image/budgets and native validation; seed approval is exhausted. |
| Candidate/locks/build qualification | `docker/presidio-bounded/`, `requirements-presidio-runtime.in`, `requirements-presidio-runtime.txt`, `scripts/check-presidio-runtime-lock.sh`, `scripts/qualify-bounded-presidio.py` | Preserve evidence/quarantined source. Remove active dependencies only after migration; do not build/remediate or select the vulnerable image as automatic rollback. |
| CI and portfolio checks | `.github/workflows/evaluate-presidio-2.2.364.yml`, `scripts/check.sh`, `scripts/qualify-supply-chain.sh` | Separate historical references from active qualification gates. Lock verification/regression checks are not Presidio remediation. Later retire only demonstrably unused workflow/dependencies. |
| Regression/security consumers | `tests/phase3/runtime/`, `tests/phase4/invocation/`, `tests/phase5/`, `tests/agents/` | Preserve redaction/authorization/containment/tenant/audit tests. Add provider-neutral equivalent assertions before retiring old implementation tests; retain historical results. |
| Architecture/operations | `docs/phase3/`, `docs/phase4/`, `docs/architecture/`, `docs/agents/`, `docs/security/`, `docs/observability.md` | Update active authority/topology/contracts only after accepted decisions. Keep dated ADRs, attribution and qualification history. |

This inventories repository consumers; it does not prove no external deployment
uses Presidio. A future retirement requires native consumer/resource verification.

## Dispatch accounting at every agent redaction site

Each admitted candidate redaction reserves two content-attempt slots before the
inspect dispatch. Count an attempt immediately before invoking the SDK method,
including auth/transport/timeout/server/output failures. Client construction,
validation, offline injected transports and scoring are not actual provider calls.
An SDK invocation is not proof of server receipt or billing. Unused reserved slots
are released; attempted slots are never refunded.

The existing core redacts user input, each retained preview, assembled prompts,
minimized tool results and the final answer. Structured tool proposals/arguments
are separately schema-validated and authorized against trusted closed source/month
selectors before dispatch. Both profiles exercise these paths. Four model requests therefore do not
mean four redactions or eight SDK attempts. A clarification still performs early
redaction; repeated conversation context adds operations. A shared
`ContentAttemptBudget` must belong to a trusted identity/campaign lifetime and
survive reset or adapter reconstruction. Current production factories do not wire
it. Metadata, if justified later, needs a separate one-attempt reservation; it is
not hidden in content accounting.

Measured with plain safe offline fixtures: financial uses three simulated model
requests/two tools and seven redactions (nine with two retained previews);
infrastructure uses four/three and nine redactions (eleven with two previews).
That corresponds to 14/18 and 18/22 injected inspect/deidentify dispatches, **zero
actual SDK attempts**. These examples illustrate amplification; they do not qualify
Google detection, latency or a live-agent budget. No agent execution is in this campaign.

The candidate uses a three-second per-RPC deadline capped by the remaining
eight-second **monotonic** overall budget, with `retry=None`. Validation time counts.
Input/output are bounded to 4,096 UTF-8 bytes, inside existing prompt/tool/final
limits; stricter 1,500-byte user/context/JSON bounds remain enforced by the core.
The outer ten-second POSIX redaction interruption remains unchanged. SDK deadlines
and local cancellation cannot undo an operation already accepted remotely. No
automatic retry, provider/region fallback or budget renewal is allowed.

Inspection rejects truncated/missing results, unknown types, malformed Unicode
ranges, inconsistent UTF-8 ranges, quotes, nested locations and all ambiguous
overlaps. Deidentification requires exact full reconstruction with bare infoType
tokens, preserved allowed text and consistent successful transformation summaries.
See [InspectResult](https://docs.cloud.google.com/sensitive-data-protection/docs/reference/rest/v2/InspectResult),
[TransformationOverview](https://docs.cloud.google.com/sensitive-data-protection/docs/reference/rest/v2/TransformationOverview)
and [type replacement](https://docs.cloud.google.com/sensitive-data-protection/docs/transformations-reference).
Offline tests use locked SDK message classes, not service replies. These strict
summary/count/replacement assumptions still need live compatibility evidence;
do not relax them silently to make a response pass. Returned-span validation cannot
find undetected sensitive spans; reviewed ground-truth scoring supplies that gate.

## Independent gateway/authentication gates

Reuse the existing [live preparation](../agents/live-preparation-status.md) and
[follow-up boundary](../agents/live-follow-up-bundle.md); do not create another
gateway/authentication architecture. Independent offline protocol tests still
exercise the actual HTTP adapter against explicit loopback doubles, including
slots, canonical tool proposals, forbidden model/tool/tenant/credential overrides,
request/token accounting and failures. This is not qualified live redaction or a
real authenticated/model-generated result.

LiteLLM still requires a separately qualified immutable image: its retained scan
has 82 HIGH/five CRITICAL and invalid duplicate evidence. An SDP image pass does
not repair that. A private key database, short-lived separately scoped client keys,
denied admin/model/expiry tests and a verified gateway-only keyless Vertex identity
remain absent. The application uses `PORTFOLIO_LITELLM_CLIENT_KEY`, never the master
key or provider credentials. Future process isolation must keep the master key
out of the application; current inequality checks alone do not establish this.

Real issuer/audience/signature/expiry validation and trusted subject-to-tenant/action
mapping are missing. UI cookie/CSRF/loopback and startup demo personas remain
simulated authentication. SDP runtime GSAs/operator credentials are not gateway
or application authority. Durable sanitized audit delivery and effective network
containment remain independent gates.

Gemini through Vertex via LiteLLM remains intended. The existing proposal's
`gemini-2.5-flash` entitlement/quota/region/tool-protocol/Arabic behavior is unproven;
reverify its documented retirement before execution rather than automatically
substituting another model. No direct provider SDK belongs in either agent.

## Ordered conditional sequence

1. Complete safe eight-class fixtures/configuration; qualify fresh artifacts and
   approve one exact synthetic SDP bundle with saved-plan/resource/IAM/network/
   release/cleanup evidence. No real-data processing is included.
2. Review results by class/language and every privacy/runtime/security/operations
   gate. Record FAIL, INCONCLUSIVE or PASS FOR FURTHER BOUNDED INTEGRATION; not
   production readiness. Preserve all failing/unexecuted cases.
3. Accept a separate provider-selection ADR for the explicitly qualified scope.
   Then implement offline trusted selection and honest neutral audit/error migration,
   with both agents, bilingual conversations, denied tools/tenants, deadlines and
   cumulative SDK budgets tested. SDP stays disabled until the authority decision.
4. Resolve independent gateway/image/real identity/key/audit/model prerequisites;
   execute only a separately authorized synthetic live-agent bundle. No SDP campaign
   approval implicitly approves external model requests.
5. Make an explicit scoped authority decision after evidence/processor/operations
   review. Startup chooses one provider; unavailable or unqualified service refuses.
6. Review consumer/resource inventory and retire obsolete Presidio implementation,
   manifests, locks and active workflows in a separate change. Preserve historical
   evidence and attribution. Verify no remaining consumers before deletion.

Do not configure the vulnerability-blocked Presidio candidate as live rollback.
If no qualified redactor is available, disable live agents and retain the explicitly
offline private bilingual demo. Replacement direction does not authorize cutover.
