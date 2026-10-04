# ADR-006: Full redaction qualification or constrained synthetic demonstration

**Status: Proposed — owner decision required; no runtime authority change.**
2026-10-04. The [bounded research decision](../../security/google-sdp-provenance-decision.md)
does not establish safe positives for five Saudi classes or Saudi phone variants.
Presidio remains authoritative and remediation remains stopped. No vulnerable
redactor is an authorized live fallback. Existing offline UI behavior is preserved.

## Options

| Choice | Benefits | Costs and unchanged requirements |
| --- | --- | --- |
| Retain full eight-class requirements; defer live cutover | Preserves arbitrary bounded free-text intent and the full financial-data boundary; no incomplete protection claim | Five class definitions/provenance sets and Saudi phone coverage remain unresolved. Keep 87-case acceptance; no execution bundle ready. |
| Separate narrower, synthetic-only demonstration | Can demonstrate orchestration/tool explanations after separate redaction/gateway/auth qualification using exclusively server-owned safe sources | Does not qualify IBAN, national/resident ID, VAT, domestic account, Saudi phone, real data or general obfuscation. Arbitrary live free-text must be unavailable, not accepted with a warning. Original 87-case/full contract remains blocked. |

**Recommendation:** retain the full requirements and defer replacement/cutover.
If a nearer live orchestration demonstration is valuable, accept option two only
as a separate scoped experiment, not as SDP replacement acceptance. It needs its
own complete reviewed corpus, acceptance, runner/image, identity/network, audit,
model and cleanup bundle. This ADR neither reduces the existing campaign nor
authorizes provider calls, scope selection, promotion or retirement.

## Enforced input boundary for the narrower option

The [unwired candidate](../../../runtime/agents/synthetic_scope_candidate.py) only
accepts exact English/Arabic server-owned phrases and finite committed source/month
selectors. It emits a new server-controlled prompt; raw browser text never leaves
that boundary. Arbitrary pasted identifiers, URLs, provider parameters, instructions
or unknown source/month cannot enter a live request. This is an allowlist, not a
sensitive-data detector. Do not expand it with permissive keyword extraction.

This reduces the **live** interaction to intent/source/month selection. The present
free-text bilingual **offline** conversation remains available and clearly simulated.
A UI must explain that difference before any approved integration; silently turning
free-text into a canned live answer is prohibited. Clarification remains within the
same identity/profile-owned conversation, accepts only finite slots and executes
no financial tool/model call until a month is resolved. Reset cannot reset global
run/identity budgets. Unknown periods return unavailable, never invented records.

Only immutable server-owned synthetic tool data and reviewed runbook sections may
reach the model. No raw evidence upload, custom paths, URLs, variable expense
records or model-authored source substitution. Candidate tenant mapping remains
server-owned; two tenants and separate registry action profiles remain enforced
by the existing runtime/invocation boundaries. Tool results/model output remain
untrusted and require schema, minimization, redaction and evidence validation.

For this separate experiment, generic email, fictional US phone and official test
card inputs plus literal reserved-domain obfuscation could be evaluated. Their
live precision/recall and byte/deadline compatibility are currently unmeasured.
Restricted inputs do not remove authoritative redaction or fail-closed behavior.
No real financial/personal/operational data is authorized; no comprehensive
financial-data protection or Saudi-residency claim follows.

## Conditional decision sequence

1. Owner selects full deferral or the separate constrained experiment explicitly.
2. Complete exact safe inputs, all supported representations and predeclared
   acceptance; freeze a matching full runner/configuration/image. No old seed
   approval or partial 42-case inventory is an executable campaign.
3. Finish independent qualified gateway, issuer/keys/server grants, scoped-key
   denial/lifecycle, durable sanitized audit, model entitlement and network gates.
4. Present one exact resources/IAM/API/calls/cost/lifetime/retention/cleanup bundle.
5. After separately approved execution, review measured evidence/UNKNOWNs.
6. Only a separately accepted provider-selection/authority decision can integrate
   SDP. Retirement then follows the [consumer inventory](../../security/google-sdp-agent-integration-retirement.md).

Failed redaction disables live execution; no fallback, warning-only bypass or
automatic rerun. The offline demo remains the available safe demonstration.
