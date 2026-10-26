'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {guideWith, INDEX} = require('./helpers');
const {TOOL_SPECS, parseStep, finalPrompt, MAX_MODEL_CALLS} = require('../src/agent');
const {maskedByteLength, MAX_TEXT_BYTES} = require('../src/clients');
const {digest} = require('../src/index-format');
const ANSWER = {action: 'answer', sources: ['p1']};
const QUESTION = 'How is the network isolated?';
const FORBIDDEN = new Set(['text', 'prompt', 'content', 'question', 'answer', 'excerpt', 'password', 'secret', 'token', 'key', 'authorization']);

function keys(value, out = new Set()) {
  if (Array.isArray(value)) value.forEach(v => keys(v, out));
  else if (value && typeof value === 'object') for (const [k, v] of Object.entries(value)) { out.add(k); keys(v, out); }
  return out;
}

test('the code copies only selected excerpts, with actual source identities and explicit assurance limits', async () => {
  const {guide, calls} = guideWith({replies: [ANSWER]});
  const result = await guide.ask(QUESTION, 'en');
  const hit = INDEX.search(QUESTION)[0];
  assert.equal(result.status, 'answered');
  assert.equal(result.answer_kind, 'document_excerpts');
  assert.equal(result.answer, hit.excerpt);
  assert.deepEqual(result.sources, [{id: hit.id, path: hit.path, heading: hit.heading, excerpt: hit.excerpt,
    excerpt_sha256: digest(hit.excerpt), identifiers_masked: false}]);
  assert.equal(result.trace.grounding_result, 'source_quotes_verified');
  assert.equal(result.source_commit, null); // This is a synthetic unbound corpus, not deployed provenance.
  assert.equal(result.corpus.id, 'synthetic-agent-fixture');
  assert.deepEqual(result.trace.tool_calls, [{tool_id: 'docs_search', rows_returned: 1}]);
  assert.equal(calls.gateway.length, MAX_MODEL_CALLS);
});

test('uncited retrieved documents never appear as used sources', async () => {
  const question = 'network onboarding keys';
  const hits = INDEX.search(question);
  assert.equal(hits.length, 3);
  const {guide} = guideWith({replies: [{action: 'answer', sources: ['p2']}]});
  const result = await guide.ask(question, 'en');
  assert.deepEqual(result.sources.map(source => source.id), [hits[1].id]);
  assert.equal(result.answer, hits[1].excerpt);
});

test('zero hits and wholly out-of-scope questions refuse without a model call or a false grounding claim', async () => {
  for (const question of ['zzzzqqqq', 'recipe cake cooking']) {
    const {guide, calls} = guideWith({replies: [{action: 'answer', text: 'Trust me.'}]});
    const result = await guide.ask(question, 'en');
    assert.deepEqual([result.status, result.reason, result.sources], ['refused', 'not_covered', []]);
    assert.equal(result.answer, undefined);
    assert.equal(calls.gateway.length, 0);
    assert.equal(result.trace.grounding_result, 'refused');
    assert.equal(result.trace.tool_calls[0].rows_returned, 0);
  }
});

test('retrieval does not force an answer when the matching passages do not cover the question', async () => {
  const {guide, calls} = guideWith({replies: [{action: 'not_covered'}]});
  const result = await guide.ask('Does the network bake cakes?', 'en');
  assert.equal(calls.gateway.length, 1);
  assert.deepEqual([result.status, result.reason, result.sources], ['refused', 'not_covered', []]);
  assert.equal(result.answer, undefined);
});

test('unsupported prose is blocked even with no numbers, matching numbers, or a valid citation', async () => {
  for (const reply of [
    {action: 'answer', text: 'Every personal identifier is masked.'},
    {action: 'answer', text: 'There are 20 administrators with unrestricted database access.'},
    {action: 'answer', sources: ['p1'], text: 'All personal data are hidden.'},
    {action: 'answer', sources: ['p1'], quote: 'A made-up quotation.'},
  ]) {
    const {guide} = guideWith({replies: [reply]});
    const result = await guide.ask(QUESTION, 'en');
    assert.deepEqual([result.status, result.reason, result.trace.grounding_result],
      ['blocked', 'unsupported_answer', 'unsupported_answer_blocked']);
    assert.equal(result.answer, undefined);
    assert.deepEqual(result.sources, []);
  }
});

test('missing, invented, duplicate, stale-turn and malformed source handles are rejected', async () => {
  for (const sources of [[], ['p1', 'p1'], ['p0'], ['p9'], ['docs/architecture.md'], ['p1', 'p2', 'p3', 'p1'], null, [1]]) {
    const {guide} = guideWith({replies: [{action: 'answer', sources}]});
    assert.equal((await guide.ask(QUESTION, 'en')).reason, 'unsupported_answer');
  }
  const {guide} = guideWith({replies: [{action: 'answer', sources: ['p2']}, {action: 'answer', sources: ['p2']}]});
  for (const question of [QUESTION, 'onboarding manifest']) {
    const result = await guide.ask(question, 'en');
    assert.equal(result.reason, 'unknown_source');
    assert.deepEqual(result.sources, []);
  }
});

test('the model cannot replace the actual question with a different search or invoke another tool', async () => {
  assert.deepEqual(Object.keys(TOOL_SPECS), ['docs_search']);
  for (const tool of ['shell', 'docs_search']) {
    const {guide} = guideWith({replies: [{action: 'tool', tool, args: {query: 'secrets'}}]});
    const result = await guide.ask(QUESTION, 'en');
    assert.equal(result.reason, 'tool_not_allowed');
  }
  assert.throws(() => parseStep('```json\n{}\n```'), /model_reply_not_json/);
});

test('the trace is the audit line and contains no question, answer, excerpt or source content', async () => {
  const {guide, lines} = guideWith({replies: [ANSWER]});
  const question = QUESTION + ' lama@example.com';
  const result = await guide.ask(question, 'en');
  assert.equal(lines.length, 1);
  const {audit_event, component, at, ...fields} = lines[0];
  assert.deepEqual(fields, result.trace);
  assert.equal(audit_event, 'guide_turn');
  assert.equal(component, 'agent-platform-guide');
  const text = JSON.stringify(result.trace);
  for (const value of [question, 'lama@example.com', result.answer, 'default-deny NetworkPolicy']) assert.ok(!text.includes(value));
  for (const key of keys(result.trace)) assert.ok(!FORBIDDEN.has(key), key);
});

test('the same request ID reaches both clients and the whole model prompt is redacted first', async () => {
  const {guide, calls} = guideWith({replies: [ANSWER]});
  const result = await guide.ask(QUESTION + ' lama@example.com', 'en');
  assert.match(result.request_id, /^[0-9a-f]{32}$/);
  for (const call of [...calls.redactor, ...calls.gateway]) assert.equal(call.headers['X-Request-ID'], result.request_id);
  assert.equal(calls.gateway[0].body.metadata.request_id, result.request_id);
  assert.equal(calls.gateway[0].headers.Authorization, 'Bearer sk-test');
  assert.ok(!JSON.stringify(calls.redactor).includes('lama@example.com'));
  assert.ok(!JSON.stringify(calls.gateway).includes('lama@example.com'));
});

test('failure of prompt redaction prevents any model call; failed output redaction releases no excerpt', async () => {
  const {guide, calls} = guideWith({replies: [ANSWER], redactorFail: true});
  assert.equal((await guide.ask(QUESTION, 'en')).reason, 'redaction_unavailable');
  assert.equal(calls.gateway.length, 0);
  const h = guideWith({replies: [ANSWER]});
  let count = 0;
  h.guide.redactor.redact = async text => {
    if (++count > 1) { const {Blocked} = require('../src/clients'); throw new Blocked('redaction_unavailable'); }
    return {text, categories: []};
  };
  const result = await h.guide.ask(QUESTION, 'en');
  assert.equal(h.calls.gateway.length, 1);
  assert.equal(result.reason, 'redaction_unavailable');
  assert.deepEqual(result.sources, []);
  assert.equal(result.answer, undefined);
});

test('worst-case Arabic UTF-8 context fits the actual client limit without silently truncating passages', () => {
  const hits = Array.from({length: 3}, (_, i) => ({id: 'chunk' + i, heading: 'ش'.repeat(120), excerpt: 'ش'.repeat(450)}));
  const {prompt, admitted} = finalPrompt('س'.repeat(500), 'ar', hits);
  assert.ok(admitted.length > 0 && admitted.length < 3);
  assert.ok(maskedByteLength(JSON.stringify(prompt)) <= MAX_TEXT_BYTES);
  assert.ok(prompt.passages.every(passage => passage.excerpt === hits[0].excerpt));
  assert.equal(prompt.passages.length, admitted.length);
});

test('cost uses the one actual gateway reply or remains unavailable', async () => {
  const h = guideWith({replies: [ANSWER]});
  assert.equal((await h.guide.ask(QUESTION, 'en')).trace.cost_usd, 0.0005);
  const unknown = guideWith({replies: [ANSWER], cost: null});
  const trace = (await unknown.guide.ask(QUESTION, 'en')).trace;
  assert.deepEqual([trace.cost_usd, trace.cost_source], [null, 'unavailable']);
});

test('input and in-memory limits refuse without a model call', async () => {
  const h = guideWith({replies: []});
  assert.equal((await h.guide.ask('', 'en')).reason, 'question_length');
  assert.equal((await h.guide.ask('hello', 'fr')).reason, 'language');
  h.guide.limits.turns = Array(30).fill(Date.now());
  assert.equal((await h.guide.ask(QUESTION, 'en')).reason, 'rate_limited');
  assert.equal(h.calls.gateway.length, 0);
});
