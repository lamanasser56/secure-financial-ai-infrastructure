'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { identifierSpans, maskSpans } = require('../src/identifiers');
const { Redactor, Blocked, maskEmails } = require('../src/clients');
const { guideWith, SEARCH } = require('./helpers');

// The same cases the Python detector is held to (platform/core/tests/test_identifiers.py).
const CASES = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../core/tests/identifier_cases.json'), 'utf8'));
const pairs = (text) => identifierSpans(text).map(([start, end, category]) => [category, text.slice(start, end)]);

test('the detector returns exactly the shared cases (parity with Python)', () => {
  for (const { text, expected } of CASES.cases) assert.deepEqual(pairs(text), expected, text);
});

test('other records\' IDs are not national IDs (owner review of #118)', () => {
  for (const text of ['Order ID 1234567890', 'Transaction ID: 1029384756']) {
    for (const shaped of [text, JSON.stringify({ question: 'x\n' + text })]) assert.deepEqual(identifierSpans(shaped), [], shaped);
  }
  assert.deepEqual(pairs('ID: 1073059188'), [['SAUDI_NATIONAL_ID', '1073059188']]);
});

test('Iqama and generic ID labels take the category from the first digit (Lama\'s review of #118)', () => {
  const expected = {
    'Iqama ID: 2123456789': 'SAUDI_RESIDENT_ID', 'Iqama ID 2123456789': 'SAUDI_RESIDENT_ID', 'ID: 2123456789': 'SAUDI_RESIDENT_ID',
    'my ID is 1073059188': 'SAUDI_NATIONAL_ID', 'Iqama Number: 2123456789': 'SAUDI_RESIDENT_ID', 'Resident ID No. 2123456789': 'SAUDI_RESIDENT_ID',
    'Residence ID 2123456789': 'SAUDI_RESIDENT_ID', 'رقم إقامتي 2123456789': 'SAUDI_RESIDENT_ID', 'ID No 1073059188': 'SAUDI_NATIONAL_ID',
    'ID Number 2123456789': 'SAUDI_RESIDENT_ID', 'Saudi ID 1073059188': 'SAUDI_NATIONAL_ID', 'ID is 2123456789': 'SAUDI_RESIDENT_ID',
    'رقمي 2123456789': 'SAUDI_RESIDENT_ID', 'هويتي رقمها 1073059188': 'SAUDI_NATIONAL_ID',
  };
  for (const [text, category] of Object.entries(expected)) {
    for (const shaped of [text, JSON.stringify({ question: 'x\n' + text })]) {
      assert.deepEqual(identifierSpans(shaped).map(([, , c]) => c), [category], shaped);
    }
  }
  for (const text of ['Order ID is 2123456789', 'Booking ID: 2123456789']) assert.deepEqual(identifierSpans(text), [], text);
  for (const text of ['Passport ID: A12345678', 'Passport No. AB1234567', 'رقم الجواز: A12345678']) {
    assert.deepEqual(identifierSpans(text), [], text); // documented gap: no qualified passport category, never mislabelled
  }
});

test('the invoice is found raw and inside a JSON string, including after an escaped newline', () => {
  for (const shaped of [CASES.invoice, JSON.stringify({ question: CASES.invoice, history: [{ q: 'x\n' + CASES.invoice }] })]) {
    const found = pairs(shaped).map(([, value]) => value);
    for (const value of CASES.invoice_values) assert.ok(found.includes(value), value);
    const masked = maskSpans(shaped, identifierSpans(shaped));
    for (const value of CASES.invoice_values) assert.ok(!masked.includes(value), value);
  }
});

test('the client sends only masked text, reports the categories, and fails closed on a residual', async () => {
  const seen = [];
  const echo = async (url, headers, body) => { seen.push(body.text); return { status: 200, headers: {}, json: { text: body.text, categories: [] } }; };
  const result = await new Redactor('k'.repeat(64), { transport: echo }).redact(CASES.invoice, 'r'.repeat(32));
  for (const value of [...CASES.invoice_values, ...CASES.invoice_emails]) assert.ok(!seen[0].includes(value), value);
  assert.deepEqual(result.categories, ['EMAIL_ADDRESS', 'IBAN_CODE', 'PHONE_NUMBER', 'SAUDI_VAT_ID']);
  const leaky = async () => ({ status: 200, headers: {}, json: { text: 'call +966 55 014 2386', categories: [] } });
  await assert.rejects(new Redactor('k'.repeat(64), { transport: leaky }).redact(CASES.invoice, 'r'.repeat(32)),
    (error) => error instanceof Blocked && error.reason === 'redaction_unavailable');
});

test('regression: tonight\'s invoice pasted into the Guide never reaches the redactor or the model raw', async () => {
  const answer = { action: 'answer', text: 'Every namespace has a default-deny NetworkPolicy.' };
  const h = guideWith({ replies: [SEARCH, answer] });
  await h.guide.ask(CASES.invoice, 'en');
  const sent = JSON.stringify([h.calls.redactor.map((c) => c.body), h.calls.gateway.map((c) => c.body)]);
  for (const value of [...CASES.invoice_values, ...CASES.invoice_emails]) assert.ok(!sent.includes(value), value);
  assert.ok(h.calls.gateway.length >= 1); // the model was reached, with masked text only
});

// Realistic-data review 2026-10: the synthetic Saudi/bilingual corpus (platform/core/tests/corpus/), the same checks as
// platform/core/tests/test_realistic_corpus.py. Every covered value is masked raw, in a JSON.stringify prompt where it
// starts a pasted line (RD-01), and in ensure_ascii-style JSON with \uXXXX-escaped Arabic digits; masking keeps JSON valid.
const CORPUS = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../core/tests/corpus/saudi_bilingual_corpus.json'), 'utf8'));
const asciiEscaped = (s) => s.replace(/[\u007f-￿]/g, (c) => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
const SHAPES = {
  raw: (text) => text,
  'guide prompt, value at a line start': (text) => JSON.stringify({ question: 'Please check this:\n' + text, history: [] }),
  'ensure_ascii JSON': (text) => asciiEscaped(JSON.stringify({ evidence: { message: '\n' + text } })),
};
const toAscii = (c) => String((c.charCodeAt(0) - (c.charCodeAt(0) >= 0x06F0 ? 0x06F0 : 0x0660)));
const normalized = (text) => text.replace(/\\u([0-9a-fA-F]{4})/g, (m, h) => String.fromCharCode(parseInt(h, 16)))
  .replace(/\p{Cf}/gu, '').replace(/[\s\-–.()+   ‑＠@]/g, '').replace(/[٠-٩۰-۹]/g, toAscii)
  .toLowerCase();
// What the Guide's client (src/clients.js redact()) sends: its email layer first, then the structured identifiers.
const masked = (text) => { const e = maskEmails(text).masked; return maskSpans(e, identifierSpans(e)); };

test('every covered corpus value is masked in every prompt shape (RD-01 to RD-04, RD-08, RD-09)', () => {
  const covered = CORPUS.items.filter((item) => item.covered);
  assert.ok(covered.length >= 180);
  for (const item of covered) {
    for (const [shape, build] of Object.entries(SHAPES)) {
      const out = normalized(masked(build(item.text)));
      for (const value of item.values) assert.ok(!out.includes(normalized(value)), item.id + ' / ' + shape);
    }
  }
});

test('every value in the pasted corpus documents is masked, and masked JSON stays valid', () => {
  for (const doc of CORPUS.documents) {
    for (const [shape, build] of Object.entries(SHAPES)) {
      const prompt = build(doc.text);
      if (shape !== 'raw') JSON.parse(maskSpans(prompt, identifierSpans(prompt))); // the identifiers layer keeps JSON valid
      const out = normalized(masked(prompt));
      for (const value of doc.values) assert.ok(!out.includes(normalized(value)), doc.id + ' / ' + shape + ' / ' + value);
    }
  }
});

test('regression RD-01: a pasted multi-line email never reaches the redactor or the model raw', async () => {
  const doc = CORPUS.documents.find((d) => d.id === 'doc_email_thread');
  const question = doc.text.slice(0, 480);
  const answer = { action: 'answer', text: 'Every namespace has a default-deny NetworkPolicy.' };
  const h = guideWith({ replies: [SEARCH, answer] });
  await h.guide.ask(question, 'en');
  const sent = normalized(JSON.stringify([h.calls.redactor.map((c) => c.body), h.calls.gateway.map((c) => c.body)]));
  const values = doc.values.filter((v) => question.includes(v));
  assert.ok(values.length >= 3);
  for (const value of values) assert.ok(!sent.includes(normalized(value)), value);
  assert.ok(h.calls.gateway.length >= 1);
});
