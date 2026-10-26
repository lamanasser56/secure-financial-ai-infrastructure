'use strict';
// Build only the reviewed current corpus. There is no recursive walk or historical fallback.
const fs = require('node:fs');
const path = require('node:path');
const {SCHEMA, MAX_CHUNK, digest, chunkId, validate} = require('../src/index-format');
const MAX_FILE = 300 * 1024;
const EXCLUDED = new Set(['handoffs', 'evidence', 'archive', 'node_modules', '.git']);
const MASKS = [
  [/projects\/[a-z][a-z0-9-]{4,28}[a-z0-9]\b/g, 'projects/PROJECT_ID'],
  [/@[a-z][a-z0-9-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com/g, '@PROJECT_ID.iam.gserviceaccount.com'],
  [/\b[a-z][a-z0-9-]{4,28}[a-z0-9]\.svc\.id\.goog\b/g, 'PROJECT_ID.svc.id.goog'],
  [/(pkg\.dev\/)[a-z][a-z0-9-]{4,28}[a-z0-9](\/)/g, '$1PROJECT_ID$2'],
  [/(--project(?:=|\s+))[a-z][a-z0-9-]{4,28}[a-z0-9]\b/g, '$1PROJECT_ID'],
  [/\b\d{10,13}\b/g, '[project-number]'],
];
const SECRET_LINE = [
  /BEGIN [A-Z ]*PRIVATE KEY/,
  /\bsk-[A-Za-z0-9]{16,}/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /\bya29\.[A-Za-z0-9_-]{20,}/,
  /\bgh[pousr]_[A-Za-z0-9]{30,}/,
  /\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}/,
  /(password|passphrase|secret|token|api[_-]?key)\s*[:=]\s*["']?[A-Za-z0-9+\/_-]{12,}/i,
  /\b[0-9a-f]{64}\b/,
];

function sanitize(text) {
  let masked = text;
  for (const [pattern, replacement] of MASKS) masked = masked.replace(pattern, replacement);
  return masked.split('\n').filter(line => !SECRET_LINE.some(pattern => pattern.test(line))).join('\n');
}

function chunks(relPath, markdown) {
  const out = [], seen = new Set();
  let heading = relPath, buffer = [], fenced = false;
  const add = text => {
    text = text.trim();
    if (!/[\p{L}\p{N}]/u.test(text.replace(/^```.*$/gm, ''))) return;
    const chunk = {path: relPath, heading, text}; chunk.id = chunkId(chunk);
    if (!seen.has(chunk.id)) { seen.add(chunk.id); out.push(chunk); }
  };
  const segmenter = new Intl.Segmenter('en', {granularity: 'sentence'});
  const flush = () => {
    const body = buffer.join('\n').trim(); buffer = [];
    for (const paragraph of body.split(/\n\s*\n/).map(value => value.trim()).filter(Boolean)) {
      if (paragraph.length <= MAX_CHUNK) { add(paragraph); continue; }
      let passage = '';
      for (const {segment} of segmenter.segment(paragraph)) {
        if (segment.trim().length > MAX_CHUNK) throw new Error('corpus:passage_too_large ' + relPath);
        if ((passage + segment).trim().length > MAX_CHUNK) { add(passage); passage = ''; }
        passage += segment;
      }
      add(passage);
    }
  };
  for (const line of markdown.split('\n')) {
    if (/^```/.test(line)) fenced = !fenced;
    const match = !fenced && /^(#{1,3})\s+(.+?)\s*#*$/.exec(line);
    if (match) { flush(); heading = match[2].slice(0, 120); } else buffer.push(line);
  }
  flush(); return out;
}

function readCorpus(file) {
  const raw = fs.readFileSync(file), value = JSON.parse(raw.toString('utf8'));
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join() !== 'files,id,reviewed_at,schema'
      || value.schema !== 1 || typeof value.id !== 'string' || !/^[a-z][a-z0-9-]{2,60}$/.test(value.id)
      || typeof value.reviewed_at !== 'string' || !/^20\d\d-\d\d-\d\d$/.test(value.reviewed_at)
      || !Array.isArray(value.files) || !value.files.length || new Set(value.files).size !== value.files.length) throw new Error('corpus:shape');
  for (const file of value.files) {
    if (typeof file !== 'string' || !/^(?:[A-Za-z0-9][A-Za-z0-9_.-]*\/)*[A-Za-z0-9][A-Za-z0-9_.-]*\.md$/.test(file)
        || file.split('/').some(part => EXCLUDED.has(part.toLowerCase()))) throw new Error('corpus:path');
  }
  return {value, sha256: digest(raw)};
}

function build(docsDir, corpusFile, {sourceCommit = null} = {}) {
  if (!corpusFile) throw new Error('corpus:required');
  if (sourceCommit !== null && (typeof sourceCommit !== 'string' || !/^[0-9a-f]{40}$/.test(sourceCommit))) throw new Error('index:source_commit');
  const root = fs.realpathSync(docsDir), corpus = readCorpus(corpusFile), documents = [], all = [];
  for (const relative of [...corpus.value.files].sort()) {
    const full = path.resolve(root, relative), real = fs.realpathSync(full);
    if (!real.startsWith(root + path.sep) || fs.lstatSync(full).isSymbolicLink() || !fs.statSync(full).isFile()) throw new Error('corpus:outside_root');
    const raw = fs.readFileSync(full);
    if (raw.length > MAX_FILE) throw new Error('corpus:file_too_large');
    const markdown = new TextDecoder('utf-8', {fatal: true}).decode(raw);
    const name = 'docs/' + relative, parts = chunks(name, sanitize(markdown));
    if (!parts.length) throw new Error('corpus:empty_document ' + name);
    documents.push({path: name, sha256: digest(raw)}); all.push(...parts);
  }
  for (const chunk of all) {
    if ([...SECRET_LINE, /\b\d{10,13}\b/].some(pattern => pattern.test(chunk.text))) throw new Error('index:secret_pattern_survived ' + chunk.path);
  }
  return validate({schema: SCHEMA, built_from: 'docs/', source_commit: sourceCommit,
    corpus: {id: corpus.value.id, reviewed_at: corpus.value.reviewed_at, manifest_sha256: corpus.sha256}, documents, chunks: all});
}

if (require.main === module) {
  const [docsDir, output, corpusFile, sourceCommit, extra] = process.argv.slice(2);
  if (!docsDir || !output || !corpusFile || !sourceCommit || extra || !/^[0-9a-f]{40}$/.test(sourceCommit)) throw new Error('usage: build-index.js <docs dir> <output> <corpus manifest> <source commit>');
  const index = build(docsDir, corpusFile, {sourceCommit});
  fs.writeFileSync(output, JSON.stringify(index));
  process.stdout.write(JSON.stringify({corpus: index.corpus.id, source_commit: index.source_commit, chunks: index.chunks.length, files: index.documents.length}) + '\n');
}

module.exports = {build, sanitize, chunks, readCorpus};
