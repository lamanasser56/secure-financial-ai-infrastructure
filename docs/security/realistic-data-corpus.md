# Realistic-data corpus (synthetic, Saudi and bilingual)

The test input of the [realistic-data review](realistic-data-review-2026-10.md): the shapes a Saudi user, an invoice or
a log really produces, in Arabic and English, so that the platform's claims are tested on more than one hand-written
example. It lives in `platform/core/tests/corpus/`:

- `make_corpus.py` generates it, deterministically;
- `saudi_bilingual_corpus.json` is the committed output, and a test checks that it equals a fresh run.

## Never real people

- **Names:** common Arabic given names joined with common family names (and their English transliterations). Person
  names are not redacted (a documented limitation); they are in the corpus to confirm that, not to test masking.
- **Email domains:** invented, with a `-fixture` label, under `.sa`, `.com.sa`, `.org.sa`, `.edu.sa` and `.net.sa`.
  There is never a `.gov.sa` domain. Every domain returned NXDOMAIN on 2026-10-19.
- **Phone numbers:** invented. They are valid in shape, so they are never dialled or messaged.
- **IBANs, national and resident IDs, and card numbers:** generated with valid checksums (mod-97, Luhn), because a
  detector that validates a checksum must be tested with values that pass it. The card numbers are public test numbers
  or generated mada-shaped numbers.

## What it contains

| Part | Count | What |
|---|---|---|
| `items` | 244 | One sensitive value in a realistic English or Arabic sentence. Each records its category, its form (how it is written) and whether the platform claims to mask it (`covered`). |
| `documents` | 6 | Pasted text: a bilingual tax invoice, a POS receipt, an email thread, a WhatsApp log, a bank SMS, and an invoice with hidden instructions (English, Arabic and zero-width spellings). Their `values` must all be masked; `gaps` holds documented gaps. |
| `injection` | 10 + 5 | Merchant names (60 characters or fewer) and container log lines with planted orders. |
| `grounding` | 15 | A stored total, an answer as a model might write it, and whether the answer is grounded. |

**The forms:**

| Category | Forms |
|---|---|
| Phones | `+966`, `00966`, `966`, `(+966)`, `05…`. Spaced, unspaced, dashed, dotted, en dash, NBSP. Arabic-Indic, Persian and mixed digits. Bidi marks around and inside the number, zero-width characters inside it. Landlines. A few non-Saudi numbers. |
| IBANs | Unspaced, in groups, lowercase, dashed, Arabic-Indic, double-spaced, with a mark inside. |
| VAT, National ID, Iqama, commercial registration numbers | With and without English and Arabic labels, including everyday phrasings (هويتي, هويتي رقمها, `ID:`, `my ID is`, Iqama ID, رقمي, رقم إقامتي). |
| IDs of unknown kind | `Iqama: 3123456789`, رقم الهوية 4123456789: a labelled ID whose first digit is neither 1 nor 2, masked as `SAUDI_ID_UNKNOWN` but not listed in the reported categories (INFO-8). |
| Passports | `Passport ID:` and رقم الجواز, as documented gaps: there is no qualified passport category (INFO-7). |
| Cards | Visa, Mastercard, Amex and mada (5888xx, 9682xx), in each grouping. |
| Emails | Plain, uppercase, angle brackets, `mailto:`, next to Arabic text, `[at]`/`[dot]`, the fullwidth at sign, and the Arabic word for "at". |

## Where it is used

- `platform/core/tests/test_realistic_corpus.py` (Python) and `platform/agents/platform-guide/test/identifiers.test.js`
  (JS). Every covered value, and every document value, must be masked after the email layer and the platform client,
  in three prompt shapes:
  - the raw text;
  - the Financial Agent's JSON prompt, with the value at the start of a pasted line;
  - `ensure_ascii` JSON, with `\uXXXX`-escaped Arabic digits.

  Masked JSON must stay valid, and amounts and injection text must be left alone. Python and JS return the same spans
  on every corpus input.
- `platform/core/tests/identifier_cases.json`: the review's own cases, which both languages must match exactly.
- `make corpus-live` (`platform/clouds/gke/corpus_live.py`): after `make up`, the corpus goes through the real
  redactor from inside the Financial Agent's Pod. It takes two measurements:
  - the redactor alone;
  - the agent's full client path.

  Leaks are decided inside the Pod, and the evidence file holds item ids, categories and booleans only.

## Changing it

1. Edit `make_corpus.py`, run it, and commit both files.
2. Add a form as `covered: true` only when the detector claims it (the docstring of
   `platform/core/src/agent_platform/identifiers.py`). Add everything else as a documented gap.
