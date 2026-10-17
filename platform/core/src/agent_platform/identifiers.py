"""Deterministic masking of structured identifiers before any text leaves for the redactor and the model.

Why: the qualified redactor policy (evaluation/google-sdp-context/policy.json) detects EMAIL_ADDRESS anywhere, but
every other pattern is anchored to the start of a line with a label (`^IBAN: ...`). The agents redact one JSON string
per model call (`json.dumps({"question": ...})`), where no line starts with a label and newlines are escaped, so a
pasted invoice reached the model with its phone numbers, IBAN and VAT number unmasked (confirmed live 2026-10-17).

This layer finds those values in raw text and inside JSON strings alike (no line anchors; JSON escapes such as \\n count
as a boundary), replaces each with its category name, and the client then refuses (fails closed) if any original value
is still in the redactor's answer. Emails are left to the existing qualified email layer and the redactor: a match that
overlaps an email address is skipped.

Covered (Western, Arabic-Indic and Persian digits; space, no-break space, thin space and hyphen as separators):
  PHONE_NUMBER        Saudi +966 / 00966 / 966 then 5X or 1X: 5X XXX XXXX, 5X-XXX-XXXX, 5XXXXXXXX, optional (0);
                      Saudi local 05X XXX XXXX, 05XXXXXXXX, 05 XXXX XXXX (and 01X landlines); any other +CC number
                      of 8-15 digits written in groups
  IBAN_CODE           SA + 2 digits + 20 characters, unspaced or in groups of four; any country's IBAN after a label
                      (IBAN, آيبان, ايبان)
  SAUDI_VAT_ID        after a label (VAT No, VAT No., VAT number, VAT #, VAT ID, VAT registration number, tax ID,
                      tax number, TRN, الرقم الضريبي, رقم ضريبي, رقم التسجيل الضريبي); a bare 15-digit 3...3 number
  CREDIT_CARD         13-19 digits (4-4-4-4, 4-6-5 or unspaced) that pass the Luhn check with a card-network prefix
  SAUDI_NATIONAL_ID   10 digits starting with 1 after a label (National ID, ID number, الهوية الوطنية, رقم الهوية)
  SAUDI_RESIDENT_ID   10 digits starting with 2 after a label (Iqama, residency number, رقم الإقامة, هوية مقيم)
  SAUDI_BANK_ACCOUNT  8-20 digits after a label (bank account, account number, رقم الحساب, الحساب البنكي)
Not covered here (left to the redactor): unlabelled national/resident IDs and bank accounts (a bare 10-digit number is
too often a timestamp), unlabelled non-Saudi IBANs, local non-Saudi phone numbers without a + prefix, and digits that
were \\u-escaped by json.dumps(ensure_ascii=True).

Known limitation: structured-ID masking currently runs in the platform client libraries (this module in Python, and
platform/agents/platform-guide/src/identifiers.js in JS). The central redactor alone catches emails only until the
qualified policy v2 (context-pattern-v2) is released, so an agent that bypasses the platform client gets email-only
protection.
"""
import re

from runtime.phase3.deterministic_email import email_spans

MAX_TEXT = 16384

_D = '[0-9\u0660-\u0669\u06F0-\u06F9]'      # a digit: Western, Arabic-Indic, Persian
_SEP = '[ \u00A0\u2009\u202F\u2011-]'          # one separator inside a number
_X = '[0-9A-Za-z\u0660-\u0669\u06F0-\u06F9]'   # an IBAN character


def _digit(chars):
    """One digit value in any of the three scripts, e.g. _digit('15') matches 1, 5, ١, ٥, ۱, ۵."""
    return '[' + ''.join(c + chr(0x0660 + int(c)) + chr(0x06F0 + int(c)) for c in chars) + ']'


_S = _SEP + '?'
_NATIONAL = _digit('15') + _D + _S + _D + '{3}' + _S + _D + '{4}' + '|' + _digit('15') + _S + _D + '{4}' + _S + _D + '{4}'
_COUNTRY = '(?:\\+' + _S + '|' + _digit('0') + '{2}' + _S + ')?' + _digit('9') + _digit('6') + _digit('6')
_B = '(?<![A-Za-z0-9_])'                    # ASCII word start (same meaning in Python and JS)
_LABEL_END = '[ \\t]{0,3}[:\uFF1A=#.-]?[ \\t]{0,3}'

# (category, priority, case-insensitive, pattern with one group "v" for the value). Lower priority wins an overlap.
# Mirrored in platform/agents/platform-guide/src/identifiers.js; tests/fixtures/identifier-cases.json binds both.
_PATTERNS = (
    ('IBAN_CODE', 0, False, '(?<![A-Za-z])(?P<v>[Ss][Aa]' + _D + '{2}(?:' + _S + _X + '{4}){5})'),
    ('IBAN_CODE', 0, True, '(?:' + _B + 'IBAN|آيبان|ايبان|الآيبان|الايبان)' + _LABEL_END
     + '(?P<v>[A-Za-z]{2}' + _D + '{2}(?:' + _S + _X + '{4}){2,7}(?:' + _S + _D + '{1,3})?)'),
    ('CREDIT_CARD', 1, False, '(?P<v>' + _D + '{4}(?:' + _S + _D + '{4}){3}(?:' + _D + '{1,3})?|' + _D + '{4}' + _S + _D + '{6}'
     + _S + _D + '{5}|' + _D + '{13,19})'),
    ('SAUDI_VAT_ID', 2, True, '(?:' + _B + 'VAT[ \\t]?(?:No\\.?|Number|#|ID|Reg(?:istration)?\\.?[ \\t]?(?:No\\.?|Number))|' + _B + 'Tax[ \\t]?(?:ID|No\\.?|Number)'
     '|' + _B + 'TRN|الرقم[ \\t]الضريبي|رقم[ \\t]ضريبي|رقم[ \\t]التسجيل[ \\t]الضريبي)' + _LABEL_END + '(?P<v>' + _D + '(?:' + _S + _D + '){9,16})'),
    ('SAUDI_NATIONAL_ID', 2, True, '(?:' + _B + 'National[ \\t]ID(?:[ \\t]No\\.?|[ \\t]Number)?|' + _B + 'ID[ \\t](?:No\\.?|Number)|' + _B + 'Identity[ \\t]Number'
     '|الهوية[ \\t]الوطنية|رقم[ \\t]الهوية)' + _LABEL_END + '(?P<v>' + _digit('1') + '(?:' + _S + _D + '){9})'),
    ('SAUDI_RESIDENT_ID', 2, True, '(?:' + _B + 'Iqama(?:[ \\t]No\\.?|[ \\t]Number)?|' + _B + 'Residency[ \\t]Number|رقم[ \\t]الإقامة|رقم[ \\t]الاقامة'
     '|هوية[ \\t]مقيم)' + _LABEL_END + '(?P<v>' + _digit('2') + '(?:' + _S + _D + '){9})'),
    ('SAUDI_BANK_ACCOUNT', 2, True, '(?:' + _B + 'Bank[ \\t]Account(?:[ \\t]No\\.?|[ \\t]Number)?|' + _B + 'Account[ \\t](?:No\\.?|Number)'
     '|رقم[ \\t]الحساب(?:[ \\t]البنكي)?|الحساب[ \\t]البنكي)' + _LABEL_END + '(?P<v>' + _D + '(?:' + _S + _D + '){7,19})'),
    ('PHONE_NUMBER', 3, False, '(?P<v>' + _COUNTRY + _S + '(?:\\(' + _digit('0') + '\\)' + _S + ')?(?:' + _NATIONAL + '))'),
    ('PHONE_NUMBER', 3, False, '(?P<v>' + _digit('0') + '(?:' + _NATIONAL + '))'),
    ('PHONE_NUMBER', 4, False, '(?P<v>\\+' + _S + '[1-9]' + _D + '{0,2}(?:' + _S + _D + '{2,4}){2,5})'),
    ('SAUDI_VAT_ID', 5, False, '(?P<v>' + _digit('3') + _D + '{13}' + _digit('3') + ')'),
)
_COMPILED = tuple((category, priority, re.compile(pattern, re.IGNORECASE if folded else 0))
                  for category, priority, folded, pattern in _PATTERNS)
_WORD = re.compile('[0-9A-Za-z\u0660-\u0669\u06F0-\u06F9]')
_DIGITS = re.compile(_D)
_CARD_PREFIX = re.compile('^(?:4|5[1-5]|2[2-7]|3[47]|6)')


def _ascii_digits(value):
    return ''.join(str(int(c)) for c in _DIGITS.findall(value))


def _luhn(digits):
    total = 0
    for index, char in enumerate(reversed(digits)):
        n = int(char) * (2 if index % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def _bounded(text, start, end):
    """No word character directly around the value; a JSON escape (\\n, \\t, \\r, \\") before it counts as a boundary."""
    if start > 0 and _WORD.match(text[start - 1]) and not (start > 1 and text[start - 2] == '\\'):
        return False
    if start > 0 and text[start - 1] == '+':
        return False
    return end == len(text) or not _WORD.match(text[end])


def _valid(category, value):
    digits = _ascii_digits(value)
    if category == 'CREDIT_CARD':
        return 13 <= len(digits) <= 19 and _CARD_PREFIX.match(digits) is not None and _luhn(digits)
    if category == 'PHONE_NUMBER' and value.lstrip().startswith('+'):
        return 8 <= len(digits) <= 15
    return True


def identifier_spans(text):
    """Sorted, non-overlapping (start, end, category) codepoint spans of the identifiers above."""
    if type(text) is not str or len(text) > MAX_TEXT:
        raise ValueError('identifiers:input')
    emails = [(start, end) for start, end, _ in email_spans(text)]
    candidates = []
    for category, priority, pattern in _COMPILED:
        for match in pattern.finditer(text):
            start, end = match.span('v')
            value = text[start:end]
            if value[-1] in ' \u00A0\u2009\u202F\u2011-':
                continue
            if not _bounded(text, start, end) or not _valid(category, value):
                continue
            if any(start < e_end and e_start < end for e_start, e_end in emails):
                continue
            candidates.append((priority, -(end - start), start, end, category))
    chosen = []
    for _, _, start, end, category in sorted(candidates):
        if all(end <= s or e <= start for s, e, _ in chosen):
            chosen.append((start, end, category))
    return sorted(chosen)


def mask(text, spans):
    pieces, cursor = [], 0
    for start, end, category in spans:
        pieces.extend((text[cursor:start], category))
        cursor = end
    pieces.append(text[cursor:])
    return ''.join(pieces)
