'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { INDEX } = require('./helpers');
const {MAX_CHUNK} = require('../src/index-format');

test('ranks the best matching chunk first and returns bounded excerpts', () => {
  const hits = INDEX.search('how do I onboard an agent manifest');
  assert.equal(hits[0].path, 'docs/agent-developer-guide.md');
  assert.ok(hits.every((h) => h.excerpt.length <= MAX_CHUNK));
});

test('no match returns nothing; at most three hits', () => {
  assert.deepEqual(INDEX.search('zzzzqqqq'), []);
  assert.ok(INDEX.search('the agent namespace secrets network').length <= 3);
});

test('results are deterministic', () => {
  assert.deepEqual(INDEX.search('secrets mounted'), INDEX.search('secrets mounted'));
});

test('Arabic lookup ignores diacritics, tatweel, alef variants and the definite article without rewriting excerpts', () => {
  const {tokens} = require('../src/search');
  assert.deepEqual(tokens('ما هِيَ البَوَّابة؟'), tokens('بوابة'));
  assert.deepEqual(tokens('إخفاء الـمعرّفات'), tokens('اخفاء معرفات'));
});
