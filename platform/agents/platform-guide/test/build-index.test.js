'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { build, sanitize } = require('../tools/build-index');

function docs(files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'guide-docs-'));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(dir, name)), { recursive: true });
    fs.writeFileSync(path.join(dir, name), text);
  }
  return dir;
}

test('project identifiers are masked and credential-looking lines are removed', () => {
  const text = [
    'Registry us-east1-docker.pkg.dev/my-demo-project-42/images/app and projects/my-demo-project-42/locations/us.',
    'Account gateway@my-demo-project-42.iam.gserviceaccount.com owns project 123456789012.',
    'api_key = sk-abcdefghijklmnopqrstuvwxyz',
    '-----BEGIN PRIVATE KEY-----',
    'digest ' + 'a'.repeat(64),
    'A normal sentence about NetworkPolicy stays.',
  ].join('\n');
  const clean = sanitize(text);
  assert.ok(!clean.includes('my-demo-project-42'));
  assert.ok(!clean.includes('123456789012'));
  assert.ok(!/sk-abc|PRIVATE KEY|a{64}/.test(clean));
  assert.ok(clean.includes('PROJECT_ID') && clean.includes('NetworkPolicy stays'));
});

test('handoffs and evidence are not indexed; chunks are bounded and carry their heading', () => {
  const dir = docs({
    'README.md': '# Title\n\n## Network\n\n' + 'Default deny applies in every namespace. '.repeat(80),
    'handoffs/notes.md': '# Private\n\nSome long private working notes that must not be indexed anywhere.',
    'evidence/run.md': '# Run\n\nEvidence file text that is long enough to be a chunk of its own here.',
  });
  const index = build(dir);
  assert.ok(index.chunks.length >= 2);
  assert.ok(index.chunks.every((c) => c.text.length <= 1200 && c.path.startsWith('docs/')));
  assert.ok(index.chunks.every((c) => !/handoffs|evidence/.test(c.path)));
  assert.ok(index.chunks.some((c) => c.heading === 'Network'));
});

test('the real docs tree builds, and nothing that looks like a project number or a key survives', () => {
  const index = build(path.join(__dirname, '..', '..', '..', '..', 'docs'));
  assert.ok(index.chunks.length > 50);
  const all = index.chunks.map((c) => c.text).join('\n');
  assert.ok(!/\b\d{12}\b/.test(all));
  assert.ok(!/BEGIN [A-Z ]*PRIVATE KEY|\bsk-[A-Za-z0-9]{16,}/.test(all));
  assert.ok(index.chunks.every((c) => !c.path.includes('handoffs')));
});
