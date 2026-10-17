'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { identifierSpans, maskSpans } = require('../src/identifiers');
const { Redactor, Blocked } = require('../src/clients');
const { guideWith, SEARCH } = require('./helpers');

// The same cases the Python detector is held to (platform/core/tests/test_identifiers.py).
const CASES = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../core/tests/identifier_cases.json'), 'utf8'));
const pairs = (text) => identifierSpans(text).map(([start, end, category]) => [category, text.slice(start, end)]);

test('the detector returns exactly the shared cases (parity with Python)', () => {
  for (const { text, expected } of CASES.cases) assert.deepEqual(pairs(text), expected, text);
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
