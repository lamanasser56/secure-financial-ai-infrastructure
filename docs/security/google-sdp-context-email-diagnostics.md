# Context-060 offline assessment

## Evidence and decision

Baseline `de9f3d1d8a5ae83f0d1fa88ac5f3e35daa1f4639` ran one frozen campaign:
59 mandatory passes, one mandatory exact-span failure at `context-060`, 120
attempted content operations, no retries or provider diagnostic. Ten mandatory
cases and all sixteen unsupported observations remain unexecuted. The retained
minimized result hash is
`6c0af896c3b2173bb56234b45f907a8f06947c16a80f7d14d1bd5c0cd8e7507a`.
Historical report, result, cleanup and validation evidence are preserved privately;
their integrity is rechecked without rewriting them or putting live text in Git.

**No concrete adapter, request, mapping or scorer defect was found. No runtime or
detector repair is justified by the retained evidence.** The existing compatibility
repair for bracketed replacements remains unchanged. Its historical context-001
cause is still UNKNOWN. This Change Set adds assessment, locked-SDK regressions and
a [minimal proposed comparison](google-sdp-email-diagnostic-execution-bundle.md).
It executes no provider request and changes no redaction authority.

## Exact trace through the frozen input

The committed synthetic fixture is `amount: fixture@example.invalid`, 31 Unicode
code points and 31 UTF-8 bytes. Its mandatory expected `EMAIL_ADDRESS` range is
`[8,31)` in both coordinate systems. The no-amount-exemption requirement remains.
The policy/corpus hashes and all 86 case classifications remain unchanged.

| Boundary | Inspected fact and consequence |
| --- | --- |
| Configuration | Built-in `EMAIL_ADDRESS`; ten distinct custom types. Global `POSSIBLE`; custom likelihoods `VERY_LIKELY`; quotes disabled. |
| Rules | Policy admits exactly four inspection-config keys. No per-type threshold, rule set, exclusion, hotword, custom detection rule, finding limit or template is supplied. No amount-field branch exists. |
| Request | `ContentItem.value` contains the entire original string. Same inspection config and text for inspect/deidentify; regional parent/endpoint pinned; `retry=None`. No table/field transformation is used. |
| Mapping | `EMAIL_ADDRESS` maps to itself. All eleven types are included in replacement transformations. Custom obfuscated email maps to the neutral email category but keeps its detector ID in scoring. |
| Offsets | Every returned finding must have an allowed type and valid half-open code-point range; supplied UTF-8 offsets must agree. Unknown, quoted, overlapping, nested or malformed locations fail closed. No invalid finding is silently filtered. |
| Output | Exact complete replacement, statistics, residual, byte, nonsensitive-text and deadline guards precede scoring. Successful empty responses allow unchanged nonsensitive text with zero transformations. |
| Scorer | Sets compare `(start,end,info_type)`; tp is intersection, fp is unexpected and fn is missing. Private spans are overwritten on every successful response, including empty results. |

The locked SDK's [3.40.0 message definitions](https://raw.githubusercontent.com/googleapis/google-cloud-python/google-cloud-dlp-v3.40.0/packages/google-cloud-dlp/google/cloud/dlp_v2/types/dlp.py)
define the request fields, repeated findings, truncation flag, UTF-8 byte ranges
and code-point ranges. Real protobuf objects and request coercion were used in
offline tests; the transport is injected and never constructs an SDK client.
The [REST inspection contract](https://docs.cloud.google.com/sensitive-data-protection/docs/reference/rest/v2/InspectConfig)
returns findings meeting the threshold, permits per-type overrides and rules,
and distinguishes quoting from type omission. Those optional overrides/rules are
absent here. The policy explicitly requests types rather than relying on defaults.

## Confirmed observations versus hypotheses

**Confirmed from the score and code:** `tp=0, fp=0, fn=1` means the actual scored
set was empty. A nonempty offset/type mismatch would produce false positives.
The successful adapter path validates and retains every finding; no provider-error
row or finite error code was emitted. This supports an empty validated inspection
finding list, without retaining a raw response. It does not reveal internal Google
candidates, likelihoods, reasons, exact receipts or billing.

Offline replay with a complete empty locked-SDK inspection response and unchanged
deidentification output reproduces that score without a provider error. This is a
valid nonsensitive-response path, not a reason to reject all empty responses.
Matching constructed findings instead produce correct replacements in English,
Arabic and mixed text, including emoji/combining characters, numeric amounts and
dates. Incorrect Arabic byte offsets fail before deidentification. Changed numeric
text fails output validation. These establish local contracts, not Google's quality.

| Candidate explanation | Evidence status |
| --- | --- |
| `.invalid` domain received insufficient built-in signals | Plausible, unproven. No returned likelihood or internal candidate evidence exists. |
| Surrounding `amount` label affected detection | Plausible, unproven. There is no application exclusion; Google context is not observed. |
| Below-`POSSIBLE` candidate was omitted | Plausible, unproven. An empty list cannot distinguish it from no candidate. |
| Service/detector variation or other provider behavior | Unproven; no diagnostic comparison or revision-specific detector evidence exists. |
| Application financial exemption, type filtering, stale spans or ASCII UTF-8 mismatch | Not supported by the traced implementation and locked-object regressions. No such code path was found. |

Google's [likelihood explanation](https://docs.cloud.google.com/sensitive-data-protection/docs/likelihood)
describes confidence based on matching signals and context. The
[infoType reference](https://docs.cloud.google.com/sensitive-data-protection/docs/infotypes-reference)
describes email detection; neither promises every syntactic reserved-domain value
under every label. The reserved domains have safe synthetic provenance under
[RFC 2606](https://www.rfc-editor.org/rfc/rfc2606); that reservation is not a
Google detection guarantee. No likelihood threshold is lowered in this work.

## Nearby email cases and unmeasured scope

`context-057`–`059` passed using `PORTFOLIO_OBFUSCATED_EMAIL` with finite `[at]`/
`[dot]` patterns, not the built-in ordinary-email detector. Their local reference
and live passes do not qualify `context-060`. The next Arabic/mixed amount-labelled
ordinary-email cases `061`/`062` did not run. The local reference's reserved-domain
regex is an assertion helper, not a Google emulator or runtime fallback.

The proposed fixed comparisons hold the threshold and all response guards constant:
the original, an email-label control, an `example.com` domain control and a mixed
numeric-only preservation control. Only finite returned-likelihood totals supplement
the existing counts. Empty totals cannot expose below-threshold candidates. This
small comparison is not a factorial study and cannot prove an internal causal
mechanism or historical failure cause. Even four clean observations cannot qualify
ten unexecuted mandatory cases, sixteen unsupported boundaries or agent inputs.

## Independent preparation that can proceed safely

Offline gateway protocol/denial/accounting regressions, trusted issuer/key-snapshot
and server-grant fixtures, scoped-key rotation/revocation contracts, tenant/database
isolation plans and durable minimized-audit design can proceed separately. They
need no SDP promotion or provider call. Actual issuer login, durable grants,
gateway database/key enforcement, deployment, cloud model identity/network and
end-to-end model execution still need concrete subjects and separate authority.
Every external model call must traverse LiteLLM; the app uses scoped client keys,
never its administrative key or direct provider credentials. Mock redaction cannot
label a qualified live path. No identity or gateway service is enabled here.

Presidio remains authoritative and remediation paused. Separate valid-identifier
research stays paused. Privacy/processor/location, independent review, complete
finite policy acceptance, provider-neutral runtime integration, repeated-turn
budgets/latency, durable audit, service provenance, real identity/tenant/database
and gateway/model qualification remain gates before any authority or retirement
decision. Historical audit UNKNOWNs and network/project-pool limitations remain.
