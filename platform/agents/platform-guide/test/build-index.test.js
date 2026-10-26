'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {build, sanitize} = require('../tools/build-index');
const {digest} = require('../src/index-format');
const {DocsIndex} = require('../src/search');

function fixture(t, files, selected = Object.keys(files)) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'guide-corpus-'));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(dir, name)), {recursive: true});
    fs.writeFileSync(path.join(dir, name), text);
  }
  const corpus = path.join(dir, 'current-docs.json');
  const manifest = {schema: 1, id: 'synthetic-current-fixture', reviewed_at: '2026-10-26', files: selected};
  fs.writeFileSync(corpus, JSON.stringify(manifest));
  return {dir, corpus, manifest};
}
const text = '# Current network\n\nThe trusted model boundary masks accepted messages before the private gateway is called.';

test('project identifiers/flags are masked and credential-looking lines removed', () => {
  const raw = [
    'Registry us-east1-docker.pkg.dev/my-demo-project-42/images/app and projects/my-demo-project-42/locations/us.',
    'Account gateway@my-demo-project-42.iam.gserviceaccount.com; --project=my-demo-project-42; --project my-demo-project-42.',
    'Project numbers 123456789012 and 1234567890.',
    'api_key = sk-abcdefghijklmnopqrstuvwxyz', '-----BEGIN PRIVATE KEY-----', 'digest ' + 'a'.repeat(64),
    'Normal NetworkPolicy documentation remains.'
  ].join('\n');
  const clean = sanitize(raw);
  assert.doesNotMatch(clean, /my-demo-project-42|1234567890|sk-abc|PRIVATE KEY|a{64}/);
  assert.match(clean, /PROJECT_ID/); assert.match(clean, /NetworkPolicy documentation remains/);
});

test('only explicitly selected current files are read; new/historical files never join implicitly', t => {
  const f = fixture(t, {'current.md': '# Current\n\n' + 'Current default-deny workload policies are declared. '.repeat(80),
    'architecture/decisions/old.md': '# Old\n\nA stale claim says workers connect directly to the database.',
    'evidence/run.md': '# Run\n\nHistorical successful count must never substitute for a current test.',
    'handoffs/private.md': '# Private\n\nPrivate work notes must not enter the model index.',
    'new-file.md': '# Unreviewed\n\nA newly added document is not automatically part of the current corpus.'}, ['current.md']);
  const index = build(f.dir, f.corpus);
  assert.deepEqual(index.documents.map(doc => doc.path), ['docs/current.md']);
  assert.ok(index.chunks.length >= 2);
  assert.ok(index.chunks.every(chunk => chunk.path === 'docs/current.md' && chunk.heading === 'Current' && chunk.text.length <= 1200));
  assert.doesNotMatch(JSON.stringify(index), /stale claim|Historical successful|Private work notes|newly added document/);
  assert.throws(() => build(f.dir), /corpus:required/);
});

test('source, manifest and original document hashes are retained with content-addressed chunks', t => {
  const f = fixture(t, {'current.md': text + '\n\napi_key = sk-abcdefghijklmnopqrstuvwxyz'});
  const index = build(f.dir, f.corpus, {sourceCommit: 'd'.repeat(40)});
  assert.equal(index.schema, 2); assert.equal(index.source_commit, 'd'.repeat(40));
  assert.equal(index.corpus.manifest_sha256, digest(fs.readFileSync(f.corpus)));
  assert.equal(index.documents[0].sha256, digest(fs.readFileSync(path.join(f.dir, 'current.md'))));
  assert.doesNotMatch(index.chunks[0].text, /api_key/);
  const runtime = new DocsIndex(index);
  assert.equal(runtime.source.source_commit, index.source_commit);
  assert.equal(runtime.chunks[0].id, index.chunks[0].id);
  assert.deepEqual(build(f.dir, f.corpus, {sourceCommit: 'd'.repeat(40)}), index);
  assert.equal(build(f.dir, f.corpus).source_commit, null); // Explicit unbound test build, never a qualified source claim.
});

test('missing, duplicate, outside, archived, symlinked, empty and oversized inputs fail closed', t => {
  const f = fixture(t, {'current.md': text});
  for (const selected of [['missing.md'], ['current.md', 'current.md'], ['../outside.md'], ['/absolute.md'],
    ['evidence/run.md'], ['handoffs/private.md'], ['archive/old.md']]) {
    fs.writeFileSync(f.corpus, JSON.stringify({...f.manifest, files: selected}));
    assert.throws(() => build(f.dir, f.corpus), undefined, selected.join(','));
  }
  fs.writeFileSync(f.corpus, JSON.stringify(f.manifest));
  fs.writeFileSync(path.join(f.dir, 'current.md'), '# Empty');
  assert.throws(() => build(f.dir, f.corpus), /empty_document/);
  fs.writeFileSync(path.join(f.dir, 'current.md'), 'x'.repeat(301 * 1024));
  assert.throws(() => build(f.dir, f.corpus), /file_too_large/);
  fs.unlinkSync(path.join(f.dir, 'current.md'));
  fs.symlinkSync(__filename, path.join(f.dir, 'current.md'));
  assert.throws(() => build(f.dir, f.corpus), /outside_root/);
});

test('runtime refuses obsolete, malformed or tampered index/source metadata', t => {
  const f = fixture(t, {'current.md': text}), valid = build(f.dir, f.corpus);
  const changes = [value => { value.schema = 1; }, value => { value.extra = true; },
    value => { value.source_commit = 'main'; }, value => { value.source_commit = ['d'.repeat(40)]; },
    value => { value.documents[0].sha256 = ['a'.repeat(64)]; }, value => { value.documents[0].path = '../private.md'; },
    value => { value.chunks[0].text += ' Undeclared change.'; }, value => { value.chunks.push({...value.chunks[0]}); },
    value => { value.corpus.manifest_sha256 = 'unknown'; }, value => { value.documents.push({...value.documents[0]}); }];
  for (const change of changes) {
    const value = structuredClone(valid); change(value); assert.throws(() => new DocsIndex(value), /index:/);
  }
});

test('production CLI requires an explicit source commit rather than silently stamping a branch', t => {
  const f = fixture(t, {'current.md': text}), output = path.join(f.dir, 'output.json');
  const script = path.join(__dirname, '../tools/build-index.js');
  for (const source of [undefined, 'main']) {
    const args = [script, f.dir, output, f.corpus, ...(source ? [source] : [])];
    assert.notEqual(spawnSync(process.execPath, args).status, 0);
    assert.equal(fs.existsSync(output), false);
  }
  assert.equal(spawnSync(process.execPath, [script, f.dir, output, f.corpus, 'e'.repeat(40)]).status, 0);
  assert.equal(JSON.parse(fs.readFileSync(output)).source_commit, 'e'.repeat(40));
});

test('the real reviewed corpus builds and current queries cannot return historical contracts', () => {
  const docs = path.resolve(__dirname, '../../../../docs'), corpus = path.join(__dirname, '../current-docs.json');
  const manifest = JSON.parse(fs.readFileSync(corpus)), index = build(docs, corpus), runtime = new DocsIndex(index);
  assert.deepEqual(index.documents.map(doc => doc.path).sort(), manifest.files.map(file => 'docs/' + file).sort());
  assert.ok(index.chunks.every(chunk => !/\/evidence\/|\/handoffs\/|\/archive\/|\/decisions\/|claims-inventory|execution-bundle/.test(chunk.path)));
  assert.doesNotMatch(index.chunks.map(chunk => chunk.text).join('\n'), /\b\d{10,13}\b|BEGIN [A-Z ]*PRIVATE KEY|\bsk-[A-Za-z0-9]{16,}/);
  for (const query of ['mandatory model boundary', 'person names passport numbers', 'executor roleRef subjects', 'in-memory quota restart', 'بوابة النموذج', 'وسيط البيانات']) {
    const hits = runtime.search(query); assert.ok(hits.length > 0, query);
    assert.ok(hits.every(hit => manifest.files.includes(hit.path.replace(/^docs\//, ''))), query);
  }
  const scope = fs.readFileSync(path.join(docs, 'security/masking-scope.md'), 'utf8');
  assert.match(scope, /Person names and passport numbers are not masked/);
  assert.match(fs.readFileSync(path.join(docs, 'agent-platform/teardown-plan.md'), 'utf8'), /explicit owner.*deletion|owner explicitly|explicit deletion|explicit.*request/i);
});
