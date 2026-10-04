# SDP agent coverage and fixture provenance

2026-10-04: **full campaign BLOCKED**. This is a preparation inventory, not
execution approval. Exact required names come from
[TrustedRuntime](../../runtime/phase3/trusted_runtime.py). No category was removed
to make qualification pass. The candidate still maps three types; no authoritative
agent factory selects it. Presidio remediation is stopped, not retired.

## Eight-class matrix

EN/AR/mixed means surrounding language, not proof of country-specific identifiers,
Arabic numeral recognition or detector accuracy. All Google precision/recall remain
unmeasured in this preparation.

| Runtime category | Proposed SDP type / official basis | EN/AR/mixed positive and negative preparation | Provenance / remaining gate |
| --- | --- | --- | --- |
| `EMAIL_ADDRESS` | `EMAIL_ADDRESS`; [built-in reference](https://docs.cloud.google.com/sensitive-data-protection/docs/infotypes-reference), reviewed custom obfuscation rule still needed | Two positives and one negative per context; additional obfuscation/Unicode/text stress | Reserved domains from `rfc2606`. Obfuscated forms preserve those domains. Built-in detection alone did not detect the historical obfuscated case. Custom rule is unimplemented and unqualified. |
| `PHONE_NUMBER` | `PHONE_NUMBER`; built-in reference | Two positives and one negative per context, Latin digits | `nanpa-reserved-555`: reserved fictional nonworking NANP range. Tests generic US format; no safe Saudi test range or Arabic-numeral/country coverage established. |
| `CREDIT_CARD` | `CREDIT_CARD_NUMBER`; built-in reference | Two positives and one negative per context; space formatting | `stripe-test-cards`: official non-production test values, not random PANs. Other networks/representations remain unqualified. |
| `IBAN_CODE` | `IBAN_CODE`; built-in reference | **BLOCKED** in all three contexts | Saudi presentation format is documented by SAMA, but its published example is not certified non-assigned. Need an authoritative safe Saudi-format test IBAN and independently verified checksum/negative rules. No plausible generated IBAN imported. |
| `SAUDI_NATIONAL_ID` | Reviewed custom detector using the [regex mechanism](https://docs.cloud.google.com/sensitive-data-protection/docs/creating-custom-infotypes-regex) | **BLOCKED** in all three contexts | No verified authoritative format/checksum and non-assigned test-value source. No pattern inferred from third-party examples. Must distinguish resident IDs and ordinary business numbers. |
| `SAUDI_RESIDENT_ID` | Reviewed custom detector | **BLOCKED** in all three contexts | Same provenance/format/checksum gate, with an independently justified neutral mapping distinct from national ID. |
| `SAUDI_VAT_ID` | Assess `VAT_NUMBER` plus reviewed custom detector; built-in reference is not Saudi coverage evidence | **BLOCKED** in all three contexts | Need authoritative Saudi format/checksum and safe test registration values. A vendor invoice example or invented dummy is insufficient. |
| `SAUDI_BANK_ACCOUNT` | Assess `FINANCIAL_ACCOUNT_NUMBER` plus reviewed custom detector | **BLOCKED** in all three contexts | First define supported bank/account-reference profiles with authoritative sources and safe test values. No universal Saudi bank-account format assumed. Preserve amounts/dates. |

No dedicated Saudi built-in was identified in the reviewed reference. That is a
documentation assessment, not an `infoTypes.list` call or proof of service absence.
Names, addresses, documents, images and image/OCR services remain out of scope.

## Provenance register

| Fixture provenance ID | Source and permitted interpretation |
| --- | --- |
| `rfc2606` | [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606): reserved example domains and `.invalid`. Mailbox text is generated within this reserved namespace. |
| `nanpa-reserved-555` | [NANPA 555 numbers](https://nanpa.com/numbering/555-line-numbers): fictional nonworking 555-0100 through 555-0199. Only those numbers under the selected NANP area code are used. This does not establish Saudi phone coverage. |
| `stripe-test-cards` | [Stripe test cards](https://docs.stripe.com/testing): official test-mode card values. No payment request, real card or live-mode payment credential is used. |
| `reserved-email-obfuscation` | Deterministic `[at]`/`[dot]` representation of an RFC-reserved mailbox. Safety provenance is RFC 2606; detection is a mandatory unqualified requirement. |
| `unicode-text-only` | Locally constructed emoji, combining marks and Arabic surrounding text around reserved values. No image input or OCR API. |
| `matched-negative-control` | Locally constructed safe amounts, dates, extension-only numbers, malformed mailbox-like text and pseudonymous tenant references; no protected identifier implied. |

[SAMA IBAN presentation](https://rulebook.sama.gov.sa/en/printed-iban-account-formats)
and the [SWIFT IBAN registry](https://www.swift.com/swift_resource/9606) support
format review, not ownership/safety of a sample account. No account value from
these sources is copied as a positive fixture. Likewise, no realistic Saudi ID,
VAT registration or bank account is generated on the assumption that it is unused.
The preserved Presidio fixture/qualification generator has local checksum construction;
passing detector tests or that construction does not certify non-assignment. Its
Saudi examples are not imported into the new SDP input set as safe provenance.

The next concrete action is to obtain authority/provider-approved **non-assigned
test values**, format/checksum rules and usage conditions for the five blocked
classes, plus the required Saudi phone variants. No external party is contacted
by this repository. When the inputs are available, review exact spans and negatives
before implementing versioned custom rules or freezing the full corpus.

## Exact partial inventory, not a substitute live campaign

[Offline fixtures](../../evaluation/google-sdp-agent/offline-fixtures.json) and
their [closed schema](../../evaluation/google-sdp-agent/offline-fixtures.schema.json)
contain **42 prepared cases**:

- 18 single-class positives: three safe classes × three contexts × two.
- Nine matched negatives: three safe classes × three contexts.
- Six multiple-identifier cases restricted to the three safe classes.
- Nine obfuscation/Unicode/OCR-like **text** cases using reserved identifiers.

The proposed 87-case campaign still lacks **45 cases**: five classes × three
contexts × (two positives + one negative). The shared stress cases also cannot
establish unsupported Saudi representations. Raw inputs have exact half-open Unicode
spans, target category, action (`redact`/`retain`) and closed provenance IDs.
They remain separate from summaries. No 87-case live corpus or executable full
campaign is represented as ready. Do not run the 42 as an easier replacement.

The loader verifies duplicate IDs/keys, byte limits, nonoverlapping exact labels,
safe positive fragments and class/context counts. No fixture text, coordinate or
text-derived hash belongs in public result artifacts, logs or UI downloads.
File-level artifact hashes identify the private input artifact, not individual text.

## Frozen acceptance and scorer scope

[Acceptance](../../evaluation/google-sdp-agent/acceptance.json) freezes zero
false negatives, zero false positives and zero protected-fragment leakage in
every required class/language cell. Mandatory negatives preserve allowed text;
mandatory positives must redact. Refusal is not a true positive. Missing denominators
remain uncovered/INCONCLUSIVE. No average overrides a failing or absent class.

[The offline scorer](../../runtime/phase3/sdp_qualification.py) matches exact
category/start/end tuples, counts repeated identifiers separately, tests protected
fragments after Unicode/case/digit normalization and requires exact allowed-text
preservation. Scorer tests replay reviewed labels solely to test scoring mechanics.
Their passing results are **not Google precision/recall or accuracy evidence**.
The offline inventory command is:

```bash
python3 scripts/inspect-sdp-qualification-preparation.py
```

It has no live mode, client construction or raw-value output. It reports BLOCKED,
42/45/87 and zero SDK attempts. Obfuscated positives remain mandatory; no fallback
or weakening of thresholds is permitted if a detector misses them.

## Raw-text processing boundary

SDP receives **original text before redaction**. This is a separate processor and
egress boundary from the subsequent redacted LiteLLM request. Future scope remains
synthetic only, trusted `us-east1`, `dlp.us-east1.rep.googleapis.com` and
`projects/PROJECT_ID/locations/us-east1`; no global/region fallback or browser override.
See Google's [location contract](https://docs.cloud.google.com/sensitive-data-protection/docs/specifying-location).
No Saudi residency, real-data privacy approval or production authorization follows.

Future runtime identity must be keyless and least privileged, distinct from operator
credentials. Reverify content permissions, GKE identity and effective egress before
any approved run. Regional endpoint pinning does not prove Layer-7/shared-IP/DNS-query
containment. The [qualification plan](google-sdp-agent-qualification-plan.md) retains
all identity, network, privacy, release, audit, cost and cleanup gates.
