'use strict';
// HTTP front of the Platform Guide. Reachable only through `kubectl port-forward` (no Service exposure, no ingress).
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { Guide } = require('./agent');
const { Redactor, Gateway } = require('./clients');
const { DocsIndex } = require('./search');
const audit = require('./audit');

const PUBLIC = path.join(__dirname, '..', 'public');
// Source and image preserve this relative layout; no runtime search or fallback copy.
const SHARED = path.resolve(__dirname, '../../../core/ui');
const sharedInventory = JSON.parse(fs.readFileSync(path.join(SHARED, 'shared-assets.json'), 'utf8'));
if (sharedInventory.version !== 1 || !sharedInventory.assets) throw new Error('guide:shared_assets');
for (const [url, type] of Object.entries(sharedInventory.assets)) {
  if (!/^\/(?:core\.js|style\.css|typeface\/[a-z0-9-]+\.woff2)$/.test(url)
      || !['text/javascript; charset=utf-8', 'text/css; charset=utf-8', 'font/woff2'].includes(type)) throw new Error('guide:shared_route');
}
const ASSETS = {
  '/': ['index.html', 'text/html; charset=utf-8'],
  '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
  '/guide.css': ['guide.css', 'text/css; charset=utf-8'],
};
const HEADERS = {
  'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; frame-ancestors 'none'; connect-src 'self'; base-uri 'none'; form-action 'none'",
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Cache-Control': 'no-store',
};
const MAX_BODY = 2048;

function createServer(guide, { hosts }) {
  const send = (response, status, body, type = 'application/json') => {
    const data = Buffer.isBuffer(body) ? body : Buffer.from(JSON.stringify(body));
    response.writeHead(status, { ...HEADERS, 'Content-Type': type, 'Content-Length': data.length });
    response.end(data);
  };
  return http.createServer((request, response) => {
    const url = request.url.split('?')[0];
    if (request.method === 'GET' && url === '/healthz') return send(response, 200, { status: 'ok' });
    if (!hosts.has(request.headers.host)) return send(response, 403, { error: 'host_rejected' });
    if (request.method === 'GET' && url === '/api/info') return send(response, 200, guide.info());
    if (request.method === 'GET' && Object.hasOwn(sharedInventory.assets, url)) {
      const file = path.resolve(SHARED, url.slice(1));
      if (!file.startsWith(SHARED + path.sep) || !fs.realpathSync(file).startsWith(fs.realpathSync(SHARED) + path.sep)) return send(response, 404, {error: 'not_found'});
      return send(response, 200, fs.readFileSync(file), sharedInventory.assets[url]);
    }
    if (request.method === 'GET' && ASSETS[url]) {
      const [file, type] = ASSETS[url];
      return send(response, 200, fs.readFileSync(path.join(PUBLIC, file)), type);
    }
    if (request.method !== 'POST' || url !== '/api/ask') return send(response, 404, { error: 'not_found' });
    if (request.headers.origin !== 'http://' + request.headers.host) return send(response, 403, { error: 'origin_rejected' });
    if (request.headers['content-type'] !== 'application/json') return send(response, 400, { error: 'json_body_required' });
    const parts = [];
    let size = 0;
    request.on('data', (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY) request.destroy();
      else parts.push(chunk);
    });
    request.on('end', async () => {
      let body;
      try {
        body = JSON.parse(Buffer.concat(parts).toString('utf8'));
      } catch {
        return send(response, 400, { error: 'json_body_required' });
      }
      if (!body || typeof body !== 'object' || Object.keys(body).sort().join() !== 'language,question') {
        return send(response, 400, { error: 'fields: question, language' });
      }
      try {
        return send(response, 200, await guide.ask(body.question, body.language));
      } catch {
        return send(response, 500, { error: 'internal' });
      }
    });
  });
}

function main() {
  const config = JSON.parse(fs.readFileSync('/secrets/agent/agent.json', 'utf8'));
  if (Object.keys(config).sort().join() !== 'gateway_key,redactor_key') throw new Error('guide:config');
  const port = Number(process.env.AGENT_PORT || 8082);
  const index = DocsIndex.load(path.join(__dirname, '..', 'docs-index.json'));
  const guide = new Guide({ index, redactor: new Redactor(config.redactor_key), gateway: new Gateway(config.gateway_key) });
  const server = createServer(guide, { hosts: new Set(['127.0.0.1:' + port]) });
  server.listen(port, '0.0.0.0', () => audit.emit('agent_started', 'agent-platform-guide', { index_chunks: index.chunks.length }));
}

if (require.main === module) main();

module.exports = { createServer };
