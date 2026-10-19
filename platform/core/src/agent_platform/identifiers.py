"""Deterministic masking of structured identifiers before any text leaves for the redactor and the model.

Why: the qualified redactor policy (evaluation/google-sdp-context/policy.json) detects EMAIL_ADDRESS anywhere, but
every other pattern is anchored to the start of a line with a label (`^IBAN: ...`). The agents redact one JSON string
per model call (`json.dumps({"question": ...})`), where no line starts with a label and newlines are escaped, so a
pasted invoice reached the model with its phone numbers, IBAN and VAT number unmasked (confirmed live 2026-10-17).

This layer finds those values in raw text and inside JSON strings alike, replaces each with its category name, and the
client then refuses (fails closed) if any original value is still in the redactor's answer.

Matching runs on a *view* of the text with an offset map, and masking uses the original positions (realistic-data review
RD-01, RD-09). In the view:
  - each JSON escape \\n \\r \\t \\b \\f \\" \\\\ \\/ reads as two spaces, so a value at the start of a pasted line inside
    json.dumps(...) or JSON.stringify(...) is seen at a line start (the letter "n" of "\\n" no longer touches it);
  - a \\uXXXX escape (json.dumps with ensure_ascii=True) reads as its character, so escaped Arabic-Indic and Persian digits
    are still digits;
  - invisible format characters (LRM, RLM, ALM, ZWSP, ZWNJ, soft hyphen, ...) are dropped, so a mark pasted inside a
    number does not split it;
  - the fullwidth at sign reads as "@".
A masked span always covers whole escapes, so masked JSON stays valid JSON.

Emails are left to the existing qualified email layer and the redactor: a match that overlaps an email address is
skipped. An address that only the view reveals (after an escaped newline, or written with the fullwidth at sign) is masked
here as EMAIL_ADDRESS, because the qualified email layer reads the original text.

Covered (Western, Arabic-Indic and Persian digits; space, no-break space, thin space and hyphen as separators; phones also
en dash and dot):
  PHONE_NUMBER        Saudi +966 / 00966 / 966 / (+966) then 5X or 1X: 5X XXX XXXX, 5X-XXX-XXXX, 5XXXXXXXX, optional (0);
                      Saudi local 05X XXX XXXX, 05XXXXXXXX, 05 XXXX XXXX, (05X) XXX XXXX (and 01X landlines); any other
                      +CC number of 8-15 digits written in groups
  IBAN_CODE           SA + 2 digits + 20 characters, unspaced or in groups of four (one or two separators between
                      groups); any country's IBAN after a label (IBAN, آيبان, ايبان)
  SAUDI_VAT_ID        after a label (VAT No, VAT No., VAT number, VAT #, VAT ID, VAT registration number, tax ID,
                      tax number, TRN, الرقم الضريبي, رقم ضريبي, رقم التسجيل الضريبي); a bare 15-digit 3...3 number
  CREDIT_CARD         13-19 digits (4-4-4-4, 4-6-5, 4-4-4-3 or unspaced) that pass the Luhn check with a card-network
                      prefix (Visa, Mastercard, Amex, 6x, and the mada-only 58xx and 9682); any Luhn-valid 16 digits
                      written 4-4-4-4
  SAUDI_NATIONAL_ID   10 digits starting with 1 after a label (National ID, ID, NID, Saudi ID, ID number, Identity
                      Number, الهوية الوطنية, رقم الهوية, الهوية, هويتي, هويتك, رقم هويتي, السجل المدني); a bare "ID"
                      is not a label after Order, Transaction, Invoice, Ref(erence), Request, Ticket, Booking,
                      رقم الطلب, رقم الفاتورة or المرجع
  SAUDI_RESIDENT_ID   10 digits starting with 2 after a label (Iqama, resident, resident ID, residency number,
                      رقم الإقامة / الاقامه, الإقامة, إقامتي, إقامتك, هوية مقيم)
  SAUDI_BANK_ACCOUNT  8-20 digits after a label (bank account, account number, رقم الحساب, الحساب البنكي)
Not covered here (left to the redactor): unlabelled national/resident IDs and bank accounts (a bare 10-digit number is
too often a timestamp), unlabelled non-Saudi IBANs, local non-Saudi phone numbers without a + prefix, commercial
registration numbers, and email addresses written with a word for "at".

Known limitation: structured-ID masking currently runs in the platform client libraries (this module in Python, and
platform/agents/platform-guide/src/identifiers.js in JS). The central redactor alone catches emails only until the
qualified policy v2 (context-pattern-v2) is released, so an agent that bypasses the platform client gets email-only
protection.
"""
import re
import unicodedata

from runtime.phase3.deterministic_email import email_spans

MAX_TEXT = 16384

_D = '[0-9\u0660-\u0669\u06F0-\u06F9]'      # a digit: Western, Arabic-Indic, Persian
_SEP = '[ \u00A0\u2009\u202F\u2011-]'          # one separator inside a number
_PSEP = '[ \u00A0\u2009\u202F\u2011\u2013.-]'  # one separator inside a phone number (also en dash and dot)
_X = '[0-9A-Za-z\u0660-\u0669\u06F0-\u06F9]'   # an IBAN character


def _digit(chars):
    """One digit value in any of the three scripts, e.g. _digit('15') matches 1, 5, ١, ٥, ۱, ۵."""
    return '[' + ''.join(c + chr(0x0660 + int(c)) + chr(0x06F0 + int(c)) for c in chars) + ']'


_S = _SEP + '?'
_S2 = _SEP + '{0,2}'                           # one or two separators (an IBAN pasted with double spaces)
_PS = _PSEP + '?'
_NATIONAL = _digit('15') + _D + _PS + _D + '{3}' + _PS + _D + '{4}' + '|' + _digit('15') + _PS + _D + '{4}' + _PS + _D + '{4}'
_CC = _digit('9') + _digit('6') + _digit('6')
_COUNTRY = '(?:\\((?:\\+|' + _digit('0') + '{2})?' + _CC + '\\)|(?:\\+' + _PS + '|' + _digit('0') + '{2}' + _PS + ')?' + _CC + ')'
_B = '(?<![A-Za-z0-9_])'                    # ASCII word start (same meaning in Python and JS)
_LABEL_END = '[ \\t]{0,3}[:\uFF1A=#.-]?[ \\t]{0,3}'

# (category, priority, case-insensitive, pattern with one group "v" for the value). Lower priority wins an overlap.
# Mirrored in platform/agents/platform-guide/src/identifiers.js; platform/core/tests/identifier_cases.json binds both.
_PATTERNS = (
    ('IBAN_CODE', 0, False, '(?<![A-Za-z])(?P<v>[Ss][Aa]' + _D + '{2}(?:' + _S2 + _X + '{4}){5})'),
    ('IBAN_CODE', 0, True, '(?:' + _B + 'IBAN|آيبان|ايبان|الآيبان|الايبان)' + _LABEL_END
     + '(?P<v>[A-Za-z]{2}' + _D + '{2}(?:' + _S2 + _X + '{4}){2,7}(?:' + _S2 + _D + '{1,3})?)'),
    ('CREDIT_CARD', 1, False, '(?P<v>' + _D + '{4}(?:' + _S + _D + '{4}){3}(?:' + _D + '{1,3})?|' + _D + '{4}' + _S + _D + '{6}'
     + _S + _D + '{5}|' + _D + '{4}(?:' + _S + _D + '{4}){2}' + _S + _D + '{3}|' + _D + '{13,19})'),
    ('SAUDI_VAT_ID', 2, True, '(?:' + _B + 'VAT[ \\t]?(?:No\\.?|Number|#|ID|Reg(?:istration)?\\.?[ \\t]?(?:No\\.?|Number))|' + _B + 'Tax[ \\t]?(?:ID|No\\.?|Number)'
     '|' + _B + 'TRN|الرقم[ \\t]الضريبي|رقم[ \\t]ضريبي|رقم[ \\t]التسجيل[ \\t]الضريبي)' + _LABEL_END + '(?P<v>' + _D + '(?:' + _S + _D + '){9,16})'),
    ('SAUDI_NATIONAL_ID', 2, True, '(?:' + _B + 'National[ \\t]ID(?:[ \\t]No\\.?|[ \\t]Number)?|' + _B + '(?:Saudi[ \\t]|N)ID(?:[ \\t](?:No\\.?|Number))?'
     '|' + _B + '(?P<bare>ID(?:[ \\t](?:No\\.?|Number))?)'
     '|' + _B + 'Identity[ \\t]Number|الهوية[ \\t]الوطنية|رقم[ \\t]الهوية|الهوية|هويتي|هويتك|السجل[ \\t]المدني)' + _LABEL_END
     + '(?P<v>' + _digit('1') + '(?:' + _S + _D + '){9})'),
    ('SAUDI_RESIDENT_ID', 2, True, '(?:' + _B + 'Iqama(?:[ \\t]No\\.?|[ \\t]Number)?|' + _B + 'Residency[ \\t]Number|' + _B + 'Resident(?:[ \\t]ID)?'
     '|(?:ال)?[اإ]قام[ةه]|[اإ]قامتي|[اإ]قامتك|هوية[ \\t]مقيم)' + _LABEL_END + '(?P<v>' + _digit('2') + '(?:' + _S + _D + '){9})'),
    ('SAUDI_BANK_ACCOUNT', 2, True, '(?:' + _B + 'Bank[ \\t]Account(?:[ \\t]No\\.?|[ \\t]Number)?|' + _B + 'Account[ \\t](?:No\\.?|Number)'
     '|رقم[ \\t]الحساب(?:[ \\t]البنكي)?|الحساب[ \\t]البنكي)' + _LABEL_END + '(?P<v>' + _D + '(?:' + _S + _D + '){7,19})'),
    ('PHONE_NUMBER', 3, False, '(?P<v>' + _COUNTRY + _PS + '(?:\\(' + _digit('0') + '\\)' + _PS + ')?(?:' + _NATIONAL + '))'),
    ('PHONE_NUMBER', 3, False, '(?P<v>' + _digit('0') + '(?:' + _NATIONAL + '))'),
    ('PHONE_NUMBER', 3, False, '(?P<v>\\(' + _digit('0') + _digit('15') + _D + '\\)' + _PS + _D + '{3}' + _PS + _D + '{4})'),
    ('PHONE_NUMBER', 4, False, '(?P<v>\\+' + _S + '[1-9]' + _D + '{0,2}(?:' + _S + _D + '{2,4}){2,5})'),
    ('SAUDI_VAT_ID', 5, False, '(?P<v>' + _digit('3') + _D + '{13}' + _digit('3') + ')'),
)
_COMPILED = tuple((category, priority, re.compile(pattern, re.IGNORECASE if folded else 0))
                  for category, priority, folded, pattern in _PATTERNS)
_WORD = re.compile('[0-9A-Za-z\u0660-\u0669\u06F0-\u06F9]')
_DIGITS = re.compile(_D)
_CARD_PREFIX = re.compile('^(?:4|5[1-5]|2[2-7]|3[47]|6|58|9682)')  # 58xx and 9682: mada-only cards (RD-03)
_GROUPED_16 = re.compile('^' + _D + '{4}(?:' + _SEP + _D + '{4}){3}$')  # 4-4-4-4 is how a card is written, any prefix
_ESCAPE = re.compile(r'\\(?:u([0-9A-Fa-f]{4})|["\\/bfnrt])')
_TRAILING = ' \u00A0\u2009\u202F\u2011\u2013.-'
_FULLWIDTH_AT = '\uFF20'
# A bare "ID" / "ID No." label is a national-ID label only when it is not some other record's ID: "Order ID 1234567890"
# and "Transaction ID: 1029384756" are not people (owner review of #118).
_OTHER_RECORD = re.compile('(?:' + _B + '(?:Order|Transaction|Invoice|Ref|Reference|Request|Ticket|Booking)|رقم[ \\t]الطلب'
                           '|رقم[ \\t]الفاتورة|المرجع)[ \\t]*[#.:-]?[ \\t]*\\n?\\Z', re.IGNORECASE)


def _ascii_digits(value):
    return ''.join(str(int(c)) for c in _DIGITS.findall(value))


def _luhn(digits):
    total = 0
    for index, char in enumerate(reversed(digits)):
        n = int(char) * (2 if index % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def _view(text):
    """(view, origin): the text as a reader sees it, and for each view character the original [start, end) it came from.
    A JSON escape becomes two spaces (\\n, \\", ...) or its character (\\uXXXX); format characters are dropped; the
    fullwidth at sign reads as "@". Both spaces of an escape map to the whole escape, so a span never cuts one in half."""
    chars, origin, i = [], [], 0
    while i < len(text):
        match = _ESCAPE.match(text, i) if text[i] == '\\' else None
        if match:
            if match.group(1):
                char = chr(int(match.group(1), 16))
                if unicodedata.category(char) != 'Cf':
                    chars.append('@' if char == _FULLWIDTH_AT else char)
                    origin.append((i, match.end()))
            else:
                chars.extend('  ')
                origin.extend([(i, match.end())] * 2)
            i = match.end()
            continue
        if unicodedata.category(text[i]) != 'Cf':
            chars.append('@' if text[i] == _FULLWIDTH_AT else text[i])
            origin.append((i, i + 1))
        i += 1
    return ''.join(chars), origin


def _bounded(view, start, end):
    """No word character directly around the value (in the view, where JSON escapes are already spaces)."""
    if start > 0 and _WORD.match(view[start - 1]):
        return False
    if start > 0 and view[start - 1] == '+':
        return False
    return end == len(view) or not _WORD.match(view[end])


def _valid(category, value):
    digits = _ascii_digits(value)
    if category == 'CREDIT_CARD':
        known = _CARD_PREFIX.match(digits) is not None or (len(digits) == 16 and _GROUPED_16.match(value) is not None)
        return 13 <= len(digits) <= 19 and known and _luhn(digits)
    if category == 'PHONE_NUMBER' and value.lstrip().startswith('+'):
        return 8 <= len(digits) <= 15
    return True


def identifier_spans(text):
    """Sorted, non-overlapping (start, end, category) codepoint spans of the identifiers above, in the original text."""
    if type(text) is not str or len(text) > MAX_TEXT:
        raise ValueError('identifiers:input')
    view, origin = _view(text)

    def original(start, end):
        return origin[start][0], origin[end - 1][1]
    emails = [(start, end) for start, end, _ in email_spans(view)]
    masked_by_email_layer = {(start, end) for start, end, _ in email_spans(text)}
    candidates = [(-1, 0, *original(start, end), 'EMAIL_ADDRESS') for start, end in emails
                  if original(start, end) not in masked_by_email_layer]
    for category, priority, pattern in _COMPILED:
        for match in pattern.finditer(view):
            start, end = match.span('v')
            value = view[start:end]
            if value[-1] in _TRAILING:
                continue
            if not _bounded(view, start, end) or not _valid(category, value):
                continue
            if 'bare' in pattern.groupindex and match.group('bare') and _OTHER_RECORD.search(view[max(0, match.start() - 40):match.start()]):
                continue
            if any(start < e_end and e_start < end for e_start, e_end in emails):
                continue
            candidates.append((priority, -(end - start), *original(start, end), category))
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
