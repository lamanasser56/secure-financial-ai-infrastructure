# ADR-007: Bounded context and pattern redaction candidate

**Status: Accepted for offline preparation only; Google behavior and promotion unproven.**
2026-10-04. The owner selected hiding explicitly labelled, sensitive-looking values,
including invalid identifiers. This is a separate candidate policy, not an amendment
that declares the original eight-class contract or historical 87-case campaign passed.
Presidio remains authoritative; its remediation remains stopped and it is not deleted.

## Scope and decision

| Activity | This candidate establishes |
| --- | --- |
| Context/pattern redaction | Finite reviewed labels, separators and value shapes with exact expected value spans. |
| Format/checksum validation | Not implemented. Invalid values can still require masking. |
| Identifier issuance/person/age inference | Not implemented; prefixes `111`, `112`, `21` convey no such inference. |
| Comprehensive real identifier detection | Not established; unlabelled and unsupported representations can be missed. |

The [rule matrix](../../security/google-sdp-context-policy.md) is the reviewed policy.
The typo `العوية` is one explicit regression case alongside the canonical Arabic
and English labels. There is no edit-distance, unrestricted fuzzy matching, Unicode
normalization or automatic spelling expansion. Input offsets refer to original text.
Unqualified variants are observations, not accepted preservation or detection cases.

Use inline custom regex detectors with capture group one identifying only the value.
Both SDK operations receive the same committed `context-pattern-v1` configuration.
The existing neutral categories are mapped explicitly; their names do not assert
issuance or official validity. Likelihood `VERY_LIKELY` describes rule matching,
not accuracy established by this campaign. Only built-in email plus the ten finite
custom types are selected; generic number, phone and card detection are not added.

Google documents [custom regex detectors](https://docs.cloud.google.com/sensitive-data-protection/docs/creating-custom-infotypes-regex)
and [likelihood/hotword rules](https://docs.cloud.google.com/sensitive-data-protection/docs/creating-custom-infotypes-likelihood).
The [SDK regex contract](https://docs.cloud.google.com/python/docs/reference/dlp/latest/google.cloud.dlp_v2.types.CustomInfoType.Regex)
supports RE2 and `group_indexes`. Actual locked SDK 3.40.0 request construction tests
cover capture-group and hotword message shapes without network calls. Proximity
hotwords adjust likelihood; they do not prove exact label attachment or negation.
The bounded alternative chosen here is anchored field/capture matching. Python
reference matching is a corpus check, not Google RE2 execution or detection evidence.

## Containment and consequences

The [candidate adapter](../../../runtime/phase3/sdp_context_policy.py) reuses the
existing [hardened adapter](../../../runtime/phase3/google_sdp_adapter.py), neutral
`RedactorClient` interface, trusted regional deployment, ADC-only identity,
three-second RPC/eight-second total deadline, zero retries and shared attempt budget.
Unknown categories, overlapping/truncated/invalid Unicode or UTF-8 spans, incomplete
transformation, leakage and oversized normalized output fail closed. SDK output
and exact transformation-statistics behavior for custom captures remain live gates.
The historical seed observed bare infoType substitutions; documented examples can
show bracketed substitutions. This candidate accepts only the existing complete
transformation contract. A mismatch blocks evaluation; do not relax it automatically.

No request chooses project, region, endpoint, custom policy or credential. No
runtime factory selects this candidate, no fallback is added, and no offline UI is
relabelled live. The future experiment reads only the exact image-bound synthetic
corpus; no text upload, arbitrary document or agent free-text crosses that boundary.

## Conditional integration and retirement

1. Execute only the separately approved [context campaign bundle](../../security/google-sdp-context-execution-bundle.md).
   All 70 mandatory cases, exact spans, preservation and provider response guards
   must pass; 16 observations retain their limitations regardless of matches.
2. Review failure modes, scope, privacy/location, latency/accounting, fresh image
   evidence, independent identity/gateway/network/audit gates and detector drift.
   A pass qualifies only this frozen synthetic policy experiment.
3. A separate authority ADR and offline integration may select a qualified candidate
   for exclusively server-controlled sources. Unrestricted live free-text remains
   blocked unless broader coverage is independently accepted.
4. Authorize any real agent run separately with exact gateway/identity/budget scope.
   Preserve tenant/profile separation, neutral fail-closed errors and all audit gates.
5. Retire Presidio only after explicit authority acceptance, complete consumer
   inventory and verified cleanup. If no qualified redactor/rollback is available,
   disable live agents and retain the offline demo; do not silently fall back.

The [full qualification plan](../../security/google-sdp-agent-qualification-plan.md),
[coverage gaps](../../security/google-sdp-agent-coverage.md) and
[retirement inventory](../../security/google-sdp-agent-integration-retirement.md)
remain unresolved. This ADR makes no real-data, Saudi-residency, production,
comprehensive typo, provider replacement or full CS6 completion claim.
