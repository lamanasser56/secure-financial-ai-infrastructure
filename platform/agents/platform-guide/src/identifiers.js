'use strict';
// Deterministic masking of structured identifiers before any text leaves for the redactor and the model. A line-for-line
// mirror of platform/core/src/agent_platform/identifiers.py (see its docstring for why and for what is covered);
// platform/core/tests/identifier_cases.json binds both: they must return exactly the same (category, value) pairs.
// Known limitation: structured-ID masking currently runs in the platform client libraries (Python + JS). The central
// redactor alone catches emails only until the qualified policy v2 (context-pattern-v2) is released, so an agent that
// bypasses the platform client gets email-only protection.

const MAX_TEXT = 16384;
const D = '[0-9\u0660-\u0669\u06F0-\u06F9]';
const SEP = '[ \u00A0\u2009\u202F\u2011-]';
const X = '[0-9A-Za-z\u0660-\u0669\u06F0-\u06F9]';
const S = SEP + '?';
const B = '(?<![A-Za-z0-9_])';

function digit(chars) {
  return '[' + [...chars].map((c) => c + String.fromCharCode(0x0660 + Number(c)) + String.fromCharCode(0x06F0 + Number(c))).join('') + ']';
}

const NATIONAL = digit('15') + D + S + D + '{3}' + S + D + '{4}' + '|' + digit('15') + S + D + '{4}' + S + D + '{4}';
const COUNTRY = '(?:\\+' + S + '|' + digit('0') + '{2}' + S + ')?' + digit('9') + digit('6') + digit('6');
const LABEL_END = '[ \\t]{0,3}[:\uFF1A=#.-]?[ \\t]{0,3}';

// [category, priority, case-insensitive, pattern with one group "v" for the value]. Lower priority wins an overlap.
const PATTERNS = [
  ['IBAN_CODE', 0, false, '(?<![A-Za-z])(?<v>[Ss][Aa]' + D + '{2}(?:' + S + X + '{4}){5})'],
  ['IBAN_CODE', 0, true, '(?:' + B + 'IBAN|آيبان|ايبان|الآيبان|الايبان)' + LABEL_END
    + '(?<v>[A-Za-z]{2}' + D + '{2}(?:' + S + X + '{4}){2,7}(?:' + S + D + '{1,3})?)'],
  ['CREDIT_CARD', 1, false, '(?<v>' + D + '{4}(?:' + S + D + '{4}){3}(?:' + D + '{1,3})?|' + D + '{4}' + S + D + '{6}'
    + S + D + '{5}|' + D + '{13,19})'],
  ['SAUDI_VAT_ID', 2, true, '(?:' + B + 'VAT[ \\t]?(?:No\\.?|Number|#|ID|Reg(?:istration)?\\.?[ \\t]?(?:No\\.?|Number))|' + B + 'Tax[ \\t]?(?:ID|No\\.?|Number)'
    + '|' + B + 'TRN|الرقم[ \\t]الضريبي|رقم[ \\t]ضريبي|رقم[ \\t]التسجيل[ \\t]الضريبي)' + LABEL_END + '(?<v>' + D + '(?:' + S + D + '){9,16})'],
  ['SAUDI_NATIONAL_ID', 2, true, '(?:' + B + 'National[ \\t]ID(?:[ \\t]No\\.?|[ \\t]Number)?|' + B + 'ID[ \\t](?:No\\.?|Number)|' + B + 'Identity[ \\t]Number'
    + '|الهوية[ \\t]الوطنية|رقم[ \\t]الهوية)' + LABEL_END + '(?<v>' + digit('1') + '(?:' + S + D + '){9})'],
  ['SAUDI_RESIDENT_ID', 2, true, '(?:' + B + 'Iqama(?:[ \\t]No\\.?|[ \\t]Number)?|' + B + 'Residency[ \\t]Number|رقم[ \\t]الإقامة|رقم[ \\t]الاقامة'
    + '|هوية[ \\t]مقيم)' + LABEL_END + '(?<v>' + digit('2') + '(?:' + S + D + '){9})'],
  ['SAUDI_BANK_ACCOUNT', 2, true, '(?:' + B + 'Bank[ \\t]Account(?:[ \\t]No\\.?|[ \\t]Number)?|' + B + 'Account[ \\t](?:No\\.?|Number)'
    + '|رقم[ \\t]الحساب(?:[ \\t]البنكي)?|الحساب[ \\t]البنكي)' + LABEL_END + '(?<v>' + D + '(?:' + S + D + '){7,19})'],
  ['PHONE_NUMBER', 3, false, '(?<v>' + COUNTRY + S + '(?:\\(' + digit('0') + '\\)' + S + ')?(?:' + NATIONAL + '))'],
  ['PHONE_NUMBER', 3, false, '(?<v>' + digit('0') + '(?:' + NATIONAL + '))'],
  ['PHONE_NUMBER', 4, false, '(?<v>\\+' + S + '[1-9]' + D + '{0,2}(?:' + S + D + '{2,4}){2,5})'],
  ['SAUDI_VAT_ID', 5, false, '(?<v>' + digit('3') + D + '{13}' + digit('3') + ')'],
].map(([category, priority, folded, pattern]) => [category, priority, new RegExp(pattern, folded ? 'gi' : 'g')]);

// The qualified Python email layer's plain-address pattern (runtime/phase3/deterministic_email.py), used only to skip
// identifiers inside an address, exactly as the Python module does.
const ATOM = "[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+";
const LABEL = '[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?';
const TLD = '(?:[A-Za-z]{2,63}|xn--[A-Za-z0-9-]{2,59})';
const EMAIL = new RegExp("(?<![A-Za-z0-9!#$%&'*+/=?^_`{|}~.@-])(" + ATOM + '(?:\\.' + ATOM + ')*@(?:' + LABEL + '\\.)+' + TLD
  + ')(?![A-Za-z0-9_@-]|\\.[A-Za-z0-9-])', 'g');

const WORD = /[0-9A-Za-z\u0660-\u0669\u06F0-\u06F9]/;
const DIGITS = /[0-9\u0660-\u0669\u06F0-\u06F9]/g;
const CARD_PREFIX = /^(?:4|5[1-5]|2[2-7]|3[47]|6)/;
const TRAILING = ' \u00A0\u2009\u202F\u2011-';

function asciiDigits(value) {
  return (value.match(DIGITS) || []).map((c) => {
    const code = c.charCodeAt(0);
    return String(code >= 0x06F0 ? code - 0x06F0 : code >= 0x0660 ? code - 0x0660 : code - 48);
  }).join('');
}

function luhn(digits) {
  let total = 0;
  [...digits].reverse().forEach((char, index) => {
    const n = Number(char) * (index % 2 ? 2 : 1);
    total += n > 9 ? n - 9 : n;
  });
  return total % 10 === 0;
}

function bounded(text, start, end) {
  if (start > 0 && WORD.test(text[start - 1]) && !(start > 1 && text[start - 2] === '\\')) return false;
  if (start > 0 && text[start - 1] === '+') return false;
  return end === text.length || !WORD.test(text[end]);
}

function valid(category, value) {
  const digits = asciiDigits(value);
  if (category === 'CREDIT_CARD') return digits.length >= 13 && digits.length <= 19 && CARD_PREFIX.test(digits) && luhn(digits);
  if (category === 'PHONE_NUMBER' && value.trimStart().startsWith('+')) return digits.length >= 8 && digits.length <= 15;
  return true;
}

// Sorted, non-overlapping [start, end, category] spans of the identifiers above.
function identifierSpans(text) {
  if (typeof text !== 'string' || text.length > MAX_TEXT) throw new Error('identifiers:input');
  const emails = [...text.matchAll(EMAIL)].map((m) => [m.index, m.index + m[1].length]);
  const candidates = [];
  for (const [category, priority, pattern] of PATTERNS) {
    for (const match of text.matchAll(pattern)) {
      const value = match.groups.v;
      const start = match.index + match[0].lastIndexOf(value);
      const end = start + value.length;
      if (TRAILING.includes(value[value.length - 1])) continue;
      if (!bounded(text, start, end) || !valid(category, value)) continue;
      if (emails.some(([s, e]) => start < e && s < end)) continue;
      candidates.push([priority, -(end - start), start, end, category]);
    }
  }
  candidates.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3] || (a[4] < b[4] ? -1 : a[4] > b[4] ? 1 : 0));
  const chosen = [];
  for (const [, , start, end, category] of candidates) {
    if (chosen.every(([s, e]) => end <= s || e <= start)) chosen.push([start, end, category]);
  }
  return chosen.sort((a, b) => a[0] - b[0]);
}

function maskSpans(text, spans) {
  let out = '';
  let cursor = 0;
  for (const [start, end, category] of spans) {
    out += text.slice(cursor, start) + category;
    cursor = end;
  }
  return out + text.slice(cursor);
}

module.exports = { identifierSpans, maskSpans };
