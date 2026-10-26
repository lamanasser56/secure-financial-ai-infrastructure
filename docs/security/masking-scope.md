# Current identifier masking scope

The executable category set is `SUPPORTED_ENTITIES` in `runtime/phase3/trusted_runtime.py`. `agent_platform.masking_scope` supplies honest English/Arabic UI descriptions. This page describes that scope; historical candidate matrices and campaign results do not broaden it.

| Category | Supported scope |
| --- | --- |
| `CREDIT_CARD` | Card numbers in supported formats with the current validation rules |
| `EMAIL_ADDRESS` | Email addresses recognized by the current chain |
| `IBAN_CODE` | Saudi formats and labelled international formats |
| `PHONE_NUMBER` | Supported Saudi and international phone formats |
| `SAUDI_BANK_ACCOUNT` | Labelled bank account numbers |
| `SAUDI_NATIONAL_ID` | Supported labelled or contextual Saudi national-ID formats |
| `SAUDI_RESIDENT_ID` | Supported labelled or contextual Saudi residence-ID formats |
| `SAUDI_VAT_ID` | Labelled or Saudi-shaped VAT/tax-ID formats |

**Person names and passport numbers are not masked.** Matching depends on format and context. It does not cover every spelling, format or kind of sensitive information. Some other labelled numeric IDs can be masked without a named category in the worker trace.

The mandatory model boundary masks each accepted message before using its private provider path. Redaction failure refuses the affected call; if it happens on a later call it does not establish that earlier calls never happened. SDK-side checks are additional protection. The absence of findings from one check does not prove that a message contained no sensitive data.

A category count is a reported detector result, not independent proof of every boundary decision or detection accuracy. Qualify actual masking with the approved synthetic corpus and exact selected images; retain false positives, false negatives, unsupported inputs and the tested context. Do not infer comprehensive personal-data protection from a passed email/phone example.
