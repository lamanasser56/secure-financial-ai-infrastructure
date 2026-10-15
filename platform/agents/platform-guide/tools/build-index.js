'use strict';
// Build-time docs index: node tools/build-index.js <docs dir> <output file>
// Reads Markdown under docs/, sanitizes it, splits it by heading into bounded chunks and writes one JSON file that is
// bundled into the image. It never runs at request time. The build FAILS if a sanitized chunk still looks like a secret.
const fs = require('node:fs');
const path = require('node:path');

const SKIP_DIRS = new Set(['handoffs', 'evidence', 'archive', 'node_modules', '.git']);
const MAX_FILE = 300 * 1024;
const MAX_CHUNK = 1200;

// Replacements: values that identify the owner's cloud project are masked, not dropped.
const MASKS = [
  [/projects\/[a-z][a-z0-9-]{4,28}[a-z0-9]\b/g, 'projects/PROJECT_ID'],
  [/@[a-z][a-z0-9-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com/g, '@PROJECT_ID.iam.gserviceaccount.com'],
  [/\b[a-z][a-z0-9-]{4,28}[a-z0-9]\.svc\.id\.goog\b/g, 'PROJECT_ID.svc.id.goog'],
  [/(pkg\.dev\/)[a-z][a-z0-9-]{4,28}[a-z0-9](\/)/g, '$1PROJECT_ID$2'],
  [/\b\d{12}\b/g, '[project-number]'],
];

// Lines that look like credentials are removed whole.
const SECRET_LINE = [
  /BEGIN [A-Z ]*PRIVATE KEY/,
  /\bsk-[A-Za-z0-9]{16,}/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /\bya29\.[A-Za-z0-9_-]{20,}/,
  /\bgh[pousr]_[A-Za-z0-9]{30,}/,
  /\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}/,
  /(password|passphrase|secret|token|api[_-]?key)\s*[:=]\s*["']?[A-Za-z0-9+\/_-]{12,}/i,
  /\b[0-9a-f]{64}\b/, // hex keys and digests of 32 bytes are not useful to a reader and may be key material
];

function sanitize(text) {
  let masked = text;
  for (const [pattern, replacement] of MASKS) masked = masked.replace(pattern, replacement);
  return masked.split('\n').filter((line) => !SECRET_LINE.some((p) => p.test(line))).join('\n');
}

function walk(dir, base = dir, found = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1))) {
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) walk(path.join(dir, entry.name), base, found);
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      const full = path.join(dir, entry.name);
      if (fs.statSync(full).size <= MAX_FILE) found.push(full);
    }
  }
  return found;
}

function chunks(relPath, markdown) {
  const out = [];
  let heading = relPath;
  let buffer = [];
  let fenced = false;
  const flush = () => {
    const body = buffer.join('\n').replace(/\n{3,}/g, '\n\n').trim();
    buffer = [];
    for (let start = 0; start < body.length; start += MAX_CHUNK) {
      const part = body.slice(start, start + MAX_CHUNK).trim();
      if (part.length >= 40) out.push({ path: relPath, heading, text: part });
    }
  };
  for (const line of markdown.split('\n')) {
    if (/^```/.test(line)) fenced = !fenced;
    const match = !fenced && /^(#{1,3})\s+(.+?)\s*#*$/.exec(line);
    if (match) {
      flush();
      heading = match[2].slice(0, 120);
    } else {
      buffer.push(line);
    }
  }
  flush();
  return out;
}

function build(docsDir, label = 'docs') {
  const all = [];
  for (const file of walk(docsDir)) {
    const rel = label + '/' + path.relative(docsDir, file).split(path.sep).join('/');
    all.push(...chunks(rel, sanitize(fs.readFileSync(file, 'utf8'))));
  }
  for (const chunk of all) {
    const flagged = [...SECRET_LINE, /\b\d{12}\b/].find((p) => p.test(chunk.text));
    if (flagged) throw new Error('index:secret_pattern_survived_in ' + chunk.path);
  }
  return { schema: 1, built_from: label + '/', chunks: all };
}

if (require.main === module) {
  const [docsDir, out] = process.argv.slice(2);
  if (!docsDir || !out) throw new Error('usage: build-index.js <docs dir> <output file>');
  const index = build(docsDir);
  if (index.chunks.length < 1) throw new Error('index:empty');
  fs.writeFileSync(out, JSON.stringify(index));
  process.stdout.write(JSON.stringify({ chunks: index.chunks.length, files: new Set(index.chunks.map((c) => c.path)).size }) + '\n');
}

module.exports = { build, sanitize, chunks, walk };
