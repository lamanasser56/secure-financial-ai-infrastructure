'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { createServer } = require('../src/server');
const { guideWith, SEARCH } = require('./helpers');

function listen(guide) {
  return new Promise((resolve) => {
    const server = createServer(guide, { hosts: new Set() });
    server.listen(0, '127.0.0.1', () => {
      const host = '127.0.0.1:' + server.address().port;
      server.close();
      const real = createServer(guide, { hosts: new Set([host]) });
      real.listen(Number(host.split(':')[1]), '127.0.0.1', () => resolve({ server: real, host }));
    });
  });
}

function request(host, { method = 'POST', url = '/api/ask', headers = {}, body }) {
  return new Promise((resolve, reject) => {
    const r = http.request({ host: '127.0.0.1', port: Number(host.split(':')[1]), method, path: url, headers: { host, ...headers } }, (res) => {
      const parts = [];
      res.on('data', (c) => parts.push(c));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(parts).toString() }));
    });
    r.on('error', reject);
    r.end(body);
  });
}

test('health, page and API rules', async () => {
  const { guide } = guideWith({ replies: [SEARCH, { action: 'answer', text: 'Every namespace has a default-deny NetworkPolicy.' }] });
  const { server, host } = await listen(guide);
  try {
    assert.equal((await request(host, { method: 'GET', url: '/healthz' })).status, 200);
    const page = await request(host, { method: 'GET', url: '/' });
    assert.equal(page.status, 200);
    assert.match(page.headers['content-security-policy'], /default-src 'none'/);
    assert.equal((await request(host, { method: 'GET', url: '/', headers: { host: 'evil.example:80' } })).status, 403);
    const json = { 'content-type': 'application/json' };
    const good = JSON.stringify({ question: 'How is the network isolated?', language: 'en' });
    assert.equal((await request(host, { headers: json, body: good })).status, 403); // no Origin
    assert.equal((await request(host, { headers: { ...json, origin: 'http://evil.example' }, body: good })).status, 403);
    assert.equal((await request(host, { headers: { ...json, origin: 'http://' + host }, body: '{"question":"x"}' })).status, 400);
    const ok = await request(host, { headers: { ...json, origin: 'http://' + host }, body: good });
    assert.equal(ok.status, 200);
    const data = JSON.parse(ok.body);
    assert.equal(data.status, 'answered');
    assert.equal(data.trace.request_id, data.request_id);
  } finally {
    server.close();
  }
});

test('the manifest and the code agree on the tool list, and the image allowlist covers every source file', () => {
  const manifest = fs.readFileSync(path.join(__dirname, '..', 'agent.yaml'), 'utf8');
  const ids = [...manifest.matchAll(/\{id: ([a-z_]+), access: read/g)].map((m) => m[1]);
  assert.deepEqual(ids, ['docs_search']);
  assert.match(manifest, /^data: none$/m);
  const ignore = fs.readFileSync(path.join(__dirname, '..', 'Dockerfile.dockerignore'), 'utf8');
  assert.ok(ignore.includes('!platform/agents/platform-guide/src/**'));
});
