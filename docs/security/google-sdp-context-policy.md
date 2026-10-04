# Context-pattern-v1 rule matrix and coverage

**Prepared and unwired.** Google detection is unmeasured. The
[ADR](../architecture/decisions/ADR-007-context-pattern-redaction-candidate.md)
defines the distinction between context masking, validation and comprehensive
identifier coverage. Source of truth: [policy](../../evaluation/google-sdp-context/policy.json),
[corpus](../../evaluation/google-sdp-context/corpus.json), exact original-codepoint
spans and [qualification record](../../evaluation/google-sdp-context/qualification.json).

## Reviewed labels and shapes

All context rows below use the field boundary described after the table. Mask only
the captured value, retain its label/separator and other text exactly. Numeric
values are ASCII or Arabic-Indic digits. A normalized category is a contract name,
not an assertion that an invalid synthetic value is an issued Saudi identifier.

| Category | Canonical labels and explicitly supported spelling variants | Candidate value shape | Preservation and unsupported boundary |
| --- | --- | --- | --- |
| `SAUDI_NATIONAL_ID` | `National ID`, `ID number`, `هوية`, `رقم الهوية`, `الهوية الوطنية`; one typo `العوية` | 4–32 digits, including deliberately invalid/overlength identity shapes | Generic `ID`, `National I.D.`, `العويه`, embedded prose and unlabelled numbers unsupported. No prefix/age inference. |
| `SAUDI_RESIDENT_ID` | `Iqama`, `residency number`, `إقامة`, `اقامة`, `رقم الإقامة`, `رقم الاقامة`, `هوية مقيم` | 4–32 digits | `الإقامه`, arbitrary missing/extra letters and unlabelled values unsupported. |
| `IBAN_CODE` | `IBAN`, `آيبان`, `ايبان` | Labelled 4–34 ASCII letters/ASCII or Arabic-Indic digits; standalone whole line `SA` + two digits + 20 alphanumeric characters | `إيبان`, embedded/grouped/partial values unsupported. No MOD97 acceptance check; invalid check digits still mask. |
| `SAUDI_BANK_ACCOUNT` | `bank account`, `bank account number`, `رقم الحساب`, `الحساب البنكي` | 4–32 digits | Generic `account`, `bank account balance`, `رقم-الحساب`, alphabetic/grouped/unlabelled numbers unsupported. |
| `SAUDI_VAT_ID` | `VAT number`, `tax ID`, `الرقم الضريبي`, `رقم ضريبي` | 4–32 digits | `VAT-number`, formatted/hyphenated/partial values and unlabelled numbers unsupported. No tax-registration validation. |
| `PHONE_NUMBER` | `phone number`, `رقم الهاتف`, `هاتف` | Optional `+`, initial/final digit, 2–29 internal digits/spaces/hyphens; standalone whole line `+` followed by 10–15 digits | Parentheses, Unicode plus, arbitrary international/Saudi formats and unlabelled local numbers unqualified. Shape does not guarantee a real phone. |
| `CREDIT_CARD` | `card number`, `رقم البطاقة` | 12–19 digits | Standalone cards, grouped digits, checksum/network inference unsupported. Official test-card value is synthetic, not a real account. |
| `EMAIL_ADDRESS` | Built-in email, without requiring a label; custom literal `[at]` / `[dot]` form | Built-in behavior unmeasured; custom ASCII local/domain components with 0–3 horizontal spaces around literal markers | `(at)/(dot)`, zero-width tricks, Unicode homoglyphs and general obfuscation unsupported. No `amount` field exemption. |

## Spacing, punctuation and exact context

- English labels are case-insensitive. Each word gap permits **one to three ASCII
  spaces or tabs**, in any mixture. No other word-gap character is selected.
- A labelled field begins a line, after at most three spaces/tabs. The separator is
  `:` / fullwidth `：` / `=` with up to three surrounding spaces/tabs, one to three
  spaces/tabs alone, or exactly one newline with up to three adjacent spaces/tabs.
- The value ends at line end after at most three spaces/tabs, or before ASCII `;`
  or `,`. Two fields on different lines are supported; arbitrary inline prose or
  multiple labels on one line is outside the context rule.
- No normalization rewrites text before matching. Zero-width joiners/nonjoiners,
  NBSP, tatweel, diacritics, CRLF label/value breaks and four-space word gaps are
  unqualified. The Python reference's case behavior does not prove RE2 equivalence.
- `not a National ID: …`, quoted labels/values, two blank lines, partial/malformed
  values and unsupported spellings are **declared observations**, not preservation
  approvals for real sensitive data. A supported labelled field followed by
  `; not a real issued identity` still requires masking the captured value.

The canonical labels, lower/uppercase English, double-space/tab gaps and five
separators are exercised by the [unit matrix](../../tests/phase3/runtime/test_sdp_context_policy.py).
These are local reference/contract assertions only. The 86-case frozen SDK campaign
samples this finite policy; it does not measure every combination against Google.
`العوية` has one corpus case and the matrix check; it does not dominate the policy.

## Synthetic provenance and acceptance

| Fixture source | What it measures; what it does not |
| --- | --- |
| Zero-filled numeric policy sentinels | Explicitly labelled numeric shapes, both digit scripts. No claim of officially reserved/nonassigned ID, bank account or Saudi phone. |
| Deliberately overlength `111`, `112`, `21` prefixes | Context masking without age/issuance inference; not valid personal identifiers. |
| `SA00` plus zero-filled payload | Demonstrably invalid IBAN check digits `00`; shape detection without checksum acceptance. |
| Zero-filled VAT sentinel | Violates the previously documented Saudi first/last-digit rule; no real registration. |
| Reserved `example.invalid` email/domain | RFC 2606 synthetic domain; built-in Google's actual treatment remains a live measurement. |
| NANPA fictional 555-0100–0199 phone range | Existing verified non-production fixture; no Saudi phone qualification. |
| Stripe official `4242` test card | Existing documented non-production test value and synthetic Arabic-digit representation; no live payment/account. |

Authoritative provenance citations and prior scope decisions remain in the
[provenance decision](google-sdp-provenance-decision.md). No random valid identifier
or real record was generated. Numeric detection does not require a `TEST` marker.

The [offline report](../../evaluation/google-sdp-context/offline-result.json) contains
only case IDs/status/counts and configuration identity: **70 required PASS, 16
OBSERVATION, zero SDK attempts**. Of 70 required cases, 63 require masking and seven
require preservation. The observations must not be counted as negative accuracy
passes. Logs/downloads never include input text, values, quotes or span locations.
Exact expected spans stay in the committed synthetic corpus, not retained results.

Amounts, SAR currency, dates, evidence IDs and pseudonymous tenant references are
preserved in multiple-field/mixed-language tests. Labels named `amount` do not
exempt embedded email/sensitive content. Scope excludes binary documents/OCR input;
unsupported obfuscation/OCR-like representations stay unqualified.

## Remaining gates

The completed run stopped at `context-001` after two invocation attempts. Its
original cause remains unknown; the remaining 85 cases were not executed.
The [offline diagnostic assessment](google-sdp-context-diagnostics.md) records a
documented replacement-format compatibility defect and a proposed first-case-only
diagnostic bundle. The separately [qualified diagnostic image](../../evaluation/google-sdp-context/diagnostic-qualification.json)
binds the changed source to fresh offline build/scan evidence for `context-001` only;
the retained qualification record applies to its historical source only. Neither
record measures current Google detection quality or authorizes execution.

Actual RE2/custom capture execution, built-in email behavior, cross-detector overlap,
exact Unicode/UTF-8 positions, complete substitution/statistics, leakage rejection,
latency and observed SDK attempts remain unproven. Local SDK object construction is
not a provider call. A policy pass does not close broad eight-class precision/recall,
valid-identifier coverage, raw-data processor/privacy/residency, repeated-agent
budgets, durable audit, identity/scoped-key/network or drift/review gates.
