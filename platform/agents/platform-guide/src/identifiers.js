'use strict';
// Deterministic masking of structured identifiers before any text leaves for the redactor and the model. A line-for-line
// mirror of platform/core/src/agent_platform/identifiers.py (see its docstring for why, for what is covered, and for the
// view with an offset map that lets values be found inside JSON.stringify output);
// platform/core/tests/identifier_cases.json binds both: they must return exactly the same (category, value) pairs.
// Known limitation: structured-ID masking currently runs in the platform client libraries (Python + JS). The central
// redactor alone catches emails only until the qualified policy v2 (context-pattern-v2) is released, so an agent that
// bypasses the platform client gets email-only protection.

const MAX_TEXT = 16384;
const D = '[0-9\u0660-\u0669\u06F0-\u06F9]';
const SEP = '[ \u00A0\u2009\u202F\u2011-]';
const PSEP = '[ \u00A0\u2009\u202F\u2011\u2013.-]'; // phones also take en dash and dot
const X = '[0-9A-Za-z\u0660-\u0669\u06F0-\u06F9]';
const S = SEP + '?';
const S2 = SEP + '{0,2}'; // one or two separators (an IBAN pasted with double spaces)
const PS = PSEP + '?';
const B = '(?<![A-Za-z0-9_])';

function digit(chars) {
  return '[' + [...chars].map((c) => c + String.fromCharCode(0x0660 + Number(c)) + String.fromCharCode(0x06F0 + Number(c))).join('') + ']';
}

const NATIONAL = digit('15') + D + PS + D + '{3}' + PS + D + '{4}' + '|' + digit('15') + PS + D + '{4}' + PS + D + '{4}';
const CC = digit('9') + digit('6') + digit('6');
const COUNTRY = '(?:\\((?:\\+|' + digit('0') + '{2})?' + CC + '\\)|(?:\\+' + PS + '|' + digit('0') + '{2}' + PS + ')?' + CC + ')';
const LABEL_END = '[ \\t]{0,3}[:\uFF1A=#.-]?[ \\t]{0,3}';

// [category, priority, case-insensitive, pattern with one group "v" for the value]. Lower priority wins an overlap.
const PATTERNS = [
  ['IBAN_CODE', 0, false, '(?<![A-Za-z])(?<v>[Ss][Aa]' + D + '{2}(?:' + S2 + X + '{4}){5})'],
  ['IBAN_CODE', 0, true, '(?:' + B + 'IBAN|آيبان|ايبان|الآيبان|الايبان)' + LABEL_END
    + '(?<v>[A-Za-z]{2}' + D + '{2}(?:' + S2 + X + '{4}){2,7}(?:' + S2 + D + '{1,3})?)'],
  ['CREDIT_CARD', 1, false, '(?<v>' + D + '{4}(?:' + S + D + '{4}){3}(?:' + D + '{1,3})?|' + D + '{4}' + S + D + '{6}'
    + S + D + '{5}|' + D + '{4}(?:' + S + D + '{4}){2}' + S + D + '{3}|' + D + '{13,19})'],
  ['SAUDI_VAT_ID', 2, true, '(?:' + B + 'VAT[ \\t]?(?:No\\.?|Number|#|ID|Reg(?:istration)?\\.?[ \\t]?(?:No\\.?|Number))|' + B + 'Tax[ \\t]?(?:ID|No\\.?|Number)'
    + '|' + B + 'TRN|الرقم[ \\t]الضريبي|رقم[ \\t]ضريبي|رقم[ \\t]التسجيل[ \\t]الضريبي)' + LABEL_END + '(?<v>' + D + '(?:' + S + D + '){9,16})'],
  ['SAUDI_ID', 2, true, '(?:' + B + 'National[ \\t]ID(?:[ \\t]No\\.?|[ \\t]Number)?|' + B + 'NID(?:[ \\t](?:No\\.?|Number))?'
    + '|' + B + 'Identity[ \\t]Number|الهوية[ \\t]الوطنية|رقم[ \\t]الهوية|الهوية|هويتي|هويتك|السجل[ \\t]المدني)' + LABEL_END
    + '(?<v>' + D + '(?:' + S + D + '){9})'],
  ['SAUDI_ID', 2, true, '(?:' + B + 'Iqama(?:[ \\t](?:ID|No\\.?|Number|#))*|' + B + 'Residen(?:cy|ce)[ \\t](?:ID|Number|Permit)(?:[ \\t](?:No\\.?|Number))?'
    + '|' + B + 'Resident(?:[ \\t]ID)?(?:[ \\t](?:No\\.?|Number))?'
    + '|(?:ال)?[اإ]قام[ةه]|[اإ]قامتي|[اإ]قامتك|هوية[ \\t]مقيم)' + LABEL_END + '(?<v>' + D + '(?:' + S + D + '){9})'],
  // A generic ID label; a bare "ID" after another record's name is skipped (see identifiers.py).
  ['SAUDI_ID', 2, true, '(?:' + B + '(?<bare>(?:my[ \\t])?ID(?:[ \\t](?:No\\.?|Number|is))?)|' + B + 'Saudi[ \\t]ID(?:[ \\t](?:No\\.?|Number))?'
    + '|رقمي|هويتي[ \\t]رقمها)' + LABEL_END + '(?<v>' + D + '(?:' + S + D + '){9})'],
  ['SAUDI_BANK_ACCOUNT', 2, true, '(?:' + B + 'Bank[ \\t]Account(?:[ \\t]No\\.?|[ \\t]Number)?|' + B + 'Account[ \\t](?:No\\.?|Number)'
    + '|رقم[ \\t]الحساب(?:[ \\t]البنكي)?|الحساب[ \\t]البنكي)' + LABEL_END + '(?<v>' + D + '(?:' + S + D + '){7,19})'],
  ['PHONE_NUMBER', 3, false, '(?<v>' + COUNTRY + PS + '(?:\\(' + digit('0') + '\\)' + PS + ')?(?:' + NATIONAL + '))'],
  ['PHONE_NUMBER', 3, false, '(?<v>' + digit('0') + '(?:' + NATIONAL + '))'],
  ['PHONE_NUMBER', 3, false, '(?<v>\\(' + digit('0') + digit('15') + D + '\\)' + PS + D + '{3}' + PS + D + '{4})'],
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
const CARD_PREFIX = /^(?:4|5[1-5]|2[2-7]|3[47]|6|58|9682)/; // 58xx and 9682: mada-only cards (RD-03)
const GROUPED_16 = new RegExp('^' + D + '{4}(?:' + SEP + D + '{4}){3}$'); // 4-4-4-4 is how a card is written, any prefix
const ESCAPE = /\\(?:u([0-9A-Fa-f]{4})|["\\/bfnrt])/y;
const FORMAT = /^\p{Cf}$/u;
const FULLWIDTH_AT = '\uFF20';
// A bare "ID" / "ID No." label is a national-ID label only when it is not some other record's ID (see identifiers.py).
const OTHER_RECORD = new RegExp('(?:' + B + '(?:Order|Transaction|Invoice|Ref|Reference|Request|Ticket|Booking)|رقم[ \\t]الطلب'
  + '|رقم[ \\t]الفاتورة|المرجع)[ \\t]*[#.:-]?[ \\t]*\\n?$', 'i');
// The 1/2 split is a naming convention only (see identifiers.py): any 10 digits after an ID label are masked.
const ID_NAMES = { 1: 'SAUDI_NATIONAL_ID', 2: 'SAUDI_RESIDENT_ID' };
const TRAILING = ' \u00A0\u2009\u202F\u2011\u2013.-';

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

// [view, origin]: the text as a reader sees it, and for each view character the original [start, end) it came from. A JSON
// escape becomes two spaces (\n, \", ...) or its character (\uXXXX); format characters are dropped; the fullwidth at
// sign reads as "@". Both spaces of an escape map to the whole escape, so a span never cuts one in half.
function view(text) {
  let out = '';
  const origin = [];
  let i = 0;
  while (i < text.length) {
    ESCAPE.lastIndex = i;
    const match = text[i] === '\\' ? ESCAPE.exec(text) : null;
    if (match) {
      const end = i + match[0].length;
      if (match[1]) {
        const char = String.fromCharCode(parseInt(match[1], 16));
        if (!FORMAT.test(char)) {
          out += char === FULLWIDTH_AT ? '@' : char;
          origin.push([i, end]);
        }
      } else {
        out += '  ';
        origin.push([i, end], [i, end]);
      }
      i = end;
      continue;
    }
    if (!FORMAT.test(text[i])) {
      out += text[i] === FULLWIDTH_AT ? '@' : text[i];
      origin.push([i, i + 1]);
    }
    i += 1;
  }
  return [out, origin];
}

function bounded(text, start, end) {
  if (start > 0 && WORD.test(text[start - 1])) return false;
  if (start > 0 && text[start - 1] === '+') return false;
  return end === text.length || !WORD.test(text[end]);
}

function valid(category, value) {
  const digits = asciiDigits(value);
  if (category === 'CREDIT_CARD') {
    const known = CARD_PREFIX.test(digits) || (digits.length === 16 && GROUPED_16.test(value));
    return digits.length >= 13 && digits.length <= 19 && known && luhn(digits);
  }
  if (category === 'PHONE_NUMBER' && value.trimStart().startsWith('+')) return digits.length >= 8 && digits.length <= 15;
  return true;
}

// Sorted, non-overlapping [start, end, category] spans of the identifiers above, in the original text. Matching runs on
// view(text); see identifiers.py for why (JSON escapes, \uXXXX digits, format characters).
function identifierSpans(text) {
  if (typeof text !== 'string' || text.length > MAX_TEXT) throw new Error('identifiers:input');
  const [seen, origin] = view(text);
  const original = (start, end) => [origin[start][0], origin[end - 1][1]];
  const emails = [...seen.matchAll(EMAIL)].map((m) => [m.index, m.index + m[1].length]);
  const maskedByEmailLayer = new Set([...text.matchAll(EMAIL)].map((m) => m.index + ':' + (m.index + m[1].length)));
  const candidates = emails.map(([s, e]) => original(s, e)).filter(([s, e]) => !maskedByEmailLayer.has(s + ':' + e))
    .map(([s, e]) => [-1, 0, s, e, 'EMAIL_ADDRESS']);
  for (const [category, priority, pattern] of PATTERNS) {
    for (const match of seen.matchAll(pattern)) {
      const value = match.groups.v;
      const start = match.index + match[0].lastIndexOf(value);
      const end = start + value.length;
      if (TRAILING.includes(value[value.length - 1])) continue;
      if (!bounded(seen, start, end) || !valid(category, value)) continue;
      if (match.groups.bare && OTHER_RECORD.test(seen.slice(Math.max(0, match.index - 40), match.index))) continue;
      if (emails.some(([s, e]) => start < e && s < end)) continue;
      const kind = category === 'SAUDI_ID' ? (ID_NAMES[asciiDigits(value)[0]] || 'SAUDI_ID_UNKNOWN') : category;
      // An ID of unknown kind yields to a phone number on the same span; still masked when nothing else matches.
      candidates.push([kind === 'SAUDI_ID_UNKNOWN' ? 3.5 : priority, -(end - start), ...original(start, end), kind]);
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
