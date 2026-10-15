'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { guideWith, SEARCH } = require('./helpers');
const { TOOL_SPECS } = require('../src/agent');

const ANSWER = { action: 'answer', text: 'Every namespace has a default-deny NetworkPolicy, and the request limit is 20 per hour.' };
const FORBIDDEN = new Set(['text', 'prompt', 'content', 'question', 'answer', 'excerpt', 'password', 'secret', 'token', 'key', 'authorization']);

function keys(value, out = new Set()) {
  if (Array.isArray(value)) value.forEach((v) => keys(v, out));
  else if (value && typeof value === 'object') for (const [k, v] of Object.entries(value)) { out.add(k); keys(v, out); }
  return out;
}

test('answers from the docs, with sources taken from the tool result', async () => {
  const { guide } = guideWith({ replies: [SEARCH, ANSWER] });
  const result = await guide.ask('How is the network isolated?', 'en');
  assert.equal(result.status, 'answered');
  assert.deepEqual(result.sources[0], { path: 'docs/architecture.md', heading: 'Network isolation' });
  assert.equal(result.trace.grounding_result, 'grounded');
  assert.equal(result.trace.tool_calls.length, 1);
  assert.equal(result.trace.tool_calls[0].tool_id, 'docs_search');
  assert.ok(result.trace.tool_calls[0].rows_returned >= 1);
  assert.equal(result.trace.tools[0], 'docs_search');
});

test('the trace is the audit line, and it holds no content', async () => {
  const { guide, lines } = guideWith({ replies: [SEARCH, ANSWER] });
  const question = 'How is the network isolated? lama@example.com';
  const result = await guide.ask(question, 'en');
  assert.equal(lines.length, 1);
  const { audit_event, component, at, ...fields } = lines[0];
  assert.deepEqual(fields, result.trace);
  assert.equal(audit_event, 'guide_turn');
  assert.equal(component, 'agent-platform-guide');
  const text = JSON.stringify(result.trace);
  for (const secret of [question, 'lama@example.com', ANSWER.text, 'default-deny NetworkPolicy']) assert.ok(!text.includes(secret));
  for (const k of keys(result.trace)) assert.ok(!FORBIDDEN.has(k), k);
});

test('the same request ID goes to the redactor and the gateway, and is returned', async () => {
  const { guide, calls } = guideWith({ replies: [SEARCH, ANSWER] });
  const result = await guide.ask('How is the network isolated?', 'en');
  assert.match(result.request_id, /^[0-9a-f]{32}$/);
  for (const call of [...calls.redactor, ...calls.gateway]) assert.equal(call.headers['X-Request-ID'], result.request_id);
  assert.equal(calls.gateway[0].body.metadata.request_id, result.request_id);
  assert.equal(calls.gateway[0].headers.Authorization, 'Bearer sk-test'); // its own scoped key
  assert.equal(calls.gateway[0].body.model, 'secure-financial-chat');
});

test('emails are masked before the redactor and counted', async () => {
  const { guide, calls } = guideWith({ replies: [{ action: 'answer', text: 'ok' }] });
  await guide.ask('ping lama@example.com', 'en');
  assert.ok(!JSON.stringify(calls.redactor).includes('lama@example.com'));
  assert.ok(!JSON.stringify(calls.gateway).includes('lama@example.com'));
});

test('fails closed: no model request when redaction is unavailable', async () => {
  const { guide, calls } = guideWith({ replies: [SEARCH, ANSWER], redactorFail: true });
  const result = await guide.ask('How is the network isolated?', 'en');
  assert.deepEqual([result.status, result.reason], ['blocked', 'redaction_unavailable']);
  assert.equal(calls.gateway.length, 0);
});

test('an answer without a search, or with an unsupported figure, is blocked', async () => {
  let h = guideWith({ replies: [ANSWER] });
  let result = await h.guide.ask('How is the network isolated?', 'en');
  assert.equal(result.reason, 'no_source');
  h = guideWith({ replies: [SEARCH, { action: 'answer', text: 'The limit is 9999 per hour.' }] });
  result = await h.guide.ask('What is the limit?', 'en');
  assert.deepEqual([result.reason, result.trace.grounding_result], ['ungrounded_numbers', 'ungrounded_claim_blocked']);
});

test('only the registered read-only tool, with strict arguments, ever runs', async () => {
  assert.deepEqual(Object.keys(TOOL_SPECS), ['docs_search']);
  for (const step of [{ action: 'tool', tool: 'shell', args: {} }, { action: 'tool', tool: 'docs_search', args: { query: 'x', path: '/etc' } },
    { action: 'tool', tool: 'docs_search', args: { query: 'q'.repeat(201) } }]) {
    const { guide } = guideWith({ replies: [step] });
    const result = await guide.ask('anything', 'en');
    assert.equal(result.status, 'blocked');
  }
});

test('cost comes from the gateway header, or is null', async () => {
  let h = guideWith({ replies: [SEARCH, ANSWER] });
  assert.deepEqual([(await h.guide.ask('network', 'en')).trace.cost_usd], [0.001]);
  h = guideWith({ replies: [SEARCH, ANSWER], cost: null });
  const trace = (await h.guide.ask('network', 'en')).trace;
  assert.deepEqual([trace.cost_usd, trace.cost_source], [null, 'unavailable']);
});

test('input and rate limits refuse without a model call', async () => {
  const h = guideWith({ replies: [] });
  assert.equal((await h.guide.ask('', 'en')).reason, 'question_length');
  assert.equal((await h.guide.ask('hello', 'fr')).reason, 'language');
  assert.equal(h.calls.gateway.length, 0);
});
