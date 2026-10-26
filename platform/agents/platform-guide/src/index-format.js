'use strict';
// One format for the build producer and runtime reader; a source reference is metadata, not a signature verdict.
const crypto = require('node:crypto');
const SCHEMA = 2;
const MAX_CHUNK = 1200;
const SHA = /^[0-9a-f]{64}$/;
const SOURCE = /^[0-9a-f]{40}$/;
const DOC = /^docs\/(?:[A-Za-z0-9][A-Za-z0-9_.-]*\/)*[A-Za-z0-9][A-Za-z0-9_.-]*\.md$/;
const digest = value => crypto.createHash('sha256').update(value).digest('hex');
const chunkId = chunk => 'c-' + digest(chunk.path + '\0' + chunk.heading + '\0' + chunk.text);
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const keys = (value, expected) => record(value) && Object.keys(value).sort().join() === [...expected].sort().join();

function validate(index) {
  if (!keys(index, ['schema', 'built_from', 'corpus', 'source_commit', 'documents', 'chunks']) || index.schema !== SCHEMA
      || index.built_from !== 'docs/' || (index.source_commit !== null && (typeof index.source_commit !== 'string' || !SOURCE.test(index.source_commit)))
      || !keys(index.corpus, ['id', 'reviewed_at', 'manifest_sha256']) || typeof index.corpus.id !== 'string' || !/^[a-z][a-z0-9-]{2,60}$/.test(index.corpus.id)
      || typeof index.corpus.reviewed_at !== 'string' || !/^20\d\d-\d\d-\d\d$/.test(index.corpus.reviewed_at)
      || typeof index.corpus.manifest_sha256 !== 'string' || !SHA.test(index.corpus.manifest_sha256)
      || !Array.isArray(index.documents) || !index.documents.length || !Array.isArray(index.chunks) || !index.chunks.length) throw new Error('index:shape');
  const paths = new Set(), ids = new Set(), covered = new Set();
  for (const doc of index.documents) {
    if (!keys(doc, ['path', 'sha256']) || typeof doc.path !== 'string' || !DOC.test(doc.path)
        || typeof doc.sha256 !== 'string' || !SHA.test(doc.sha256) || paths.has(doc.path)) throw new Error('index:document');
    paths.add(doc.path);
  }
  for (const chunk of index.chunks) {
    if (!keys(chunk, ['id', 'path', 'heading', 'text']) || !paths.has(chunk.path) || typeof chunk.heading !== 'string'
        || !chunk.heading || chunk.heading.length > 120 || typeof chunk.text !== 'string' || chunk.text.length < 40
        || chunk.text.length > MAX_CHUNK || chunk.id !== chunkId(chunk) || ids.has(chunk.id)) throw new Error('index:chunk');
    ids.add(chunk.id); covered.add(chunk.path);
  }
  if (covered.size !== paths.size) throw new Error('index:empty_document');
  return index;
}

module.exports = {SCHEMA, MAX_CHUNK, digest, chunkId, validate};
