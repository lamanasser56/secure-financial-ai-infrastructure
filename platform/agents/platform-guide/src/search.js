'use strict';
// docs_search: BM25 over the chunks bundled at build time. Read-only, in-process, no network.
const fs = require('node:fs');
const {validate, MAX_CHUNK} = require('./index-format');

const K1 = 1.5;
const B = 0.75;
const TOP = 3;
const EXCERPT = MAX_CHUNK;
const STOP = new Set(['the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'is', 'it', 'on', 'for', 'how', 'what', 'does', 'do', 'with',
  'this', 'that', 'are', 'be', 'by', 'as', 'at', 'from', 'can', 'i', 'my', 'me',
  'ما', 'هي', 'هو', 'كيف', 'عن', 'هذا', 'هذه', 'هل', 'في', 'من', 'علي', 'الي', 'مع', 'او', 'التي', 'الذي', 'ان', 'لا']);

function tokens(text) {
  const out = [];
  const normalized = String(text).toLowerCase().normalize('NFKC').replace(/[\u064b-\u065f\u0670\u0640]/g, '').replace(/[أإآ]/g, 'ا').replace(/ى/g, 'ي');
  for (let t of normalized.split(/[^\p{L}\p{N}_]+/u)) {
    if (/^ال[\u0621-\u064a]{3,}$/.test(t)) t = t.slice(2);
    if (t.length > 1 && !STOP.has(t)) out.push(t);
  }
  return out;
}

class DocsIndex {
  constructor(index) {
    validate(index);
    this.source = {source_commit: index.source_commit, corpus: {...index.corpus}, documents: index.documents.map(doc => ({...doc}))};
    this.chunks = index.chunks.map(chunk => ({...chunk}));
    this.docs = this.chunks.map((c) => {
      const counts = new Map();
      for (const t of [...tokens(c.text), ...tokens(c.heading), ...tokens(c.heading)]) counts.set(t, (counts.get(t) || 0) + 1);
      let length = 0;
      for (const n of counts.values()) length += n;
      return { counts, length };
    });
    this.average = this.docs.reduce((s, d) => s + d.length, 0) / Math.max(1, this.docs.length);
    this.frequency = new Map();
    for (const d of this.docs) for (const t of d.counts.keys()) this.frequency.set(t, (this.frequency.get(t) || 0) + 1);
  }

  static load(file) {
    return new DocsIndex(JSON.parse(fs.readFileSync(file, 'utf8')));
  }

  search(query, limit = TOP) {
    const terms = [...new Set(tokens(query))];
    const n = this.docs.length;
    const scored = [];
    this.docs.forEach((d, i) => {
      let score = 0;
      for (const t of terms) {
        const f = d.counts.get(t);
        if (!f) continue;
        const df = this.frequency.get(t);
        const idf = Math.log(1 + (n - df + 0.5) / (df + 0.5));
        score += idf * ((f * (K1 + 1)) / (f + K1 * (1 - B + (B * d.length) / this.average)));
      }
      if (score > 0) scored.push({ i, score });
    });
    scored.sort((a, b) => b.score - a.score || a.i - b.i);
    return scored.slice(0, limit).map(({ i, score }) => ({
      id: this.chunks[i].id,
      path: this.chunks[i].path,
      heading: this.chunks[i].heading,
      excerpt: this.chunks[i].text,
      score: Math.round(score * 100) / 100,
    }));
  }
}

module.exports = { DocsIndex, tokens, EXCERPT, TOP };
