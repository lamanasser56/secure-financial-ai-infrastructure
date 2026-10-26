'use strict';
const { DocsIndex } = require('../src/search');
const { Guide } = require('../src/agent');
const { Redactor, Gateway } = require('../src/clients');

// Hermetic source fixtures for turn/transport tests. Real current-corpus retrieval is tested separately.
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const {build} = require('../tools/build-index');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'guide-fixture-'));
let INDEX;
try {
  const documents = [
    ['architecture.md', 'Network isolation', 'Every managed namespace has a default-deny NetworkPolicy. Workers use the trusted model boundary. The Financial request limit is 20 per hour.'],
    ['agent-developer-guide.md', 'Onboarding', 'Run make onboard A=my-agent to validate the manifest. This synthetic fixture permits a budget of at most 5.00 dollars per month.'],
    ['security/threat-model.md', 'Secrets', 'Keys live in Kubernetes Secrets mounted read-only into the workload that owns them. Workers do not hold private provider credentials.']
  ];
  for (const [name, heading, text] of documents) {
    fs.mkdirSync(path.dirname(path.join(temporary, name)), {recursive: true});
    fs.writeFileSync(path.join(temporary, name), '# ' + heading + '\n\n' + text);
  }
  const manifest = path.join(temporary, 'current-docs.json');
  fs.writeFileSync(manifest, JSON.stringify({schema: 1, id: 'synthetic-agent-fixture', reviewed_at: '2026-10-26', files: documents.map(row => row[0])}));
  INDEX = new DocsIndex(build(temporary, manifest));
} finally { fs.rmSync(temporary, {recursive: true, force: true}); }


// Scripted fakes for the two platform clients' transports. `redactorStatus` etc. let a test break one hop.
function fakes({ replies, cost = '0.0005', redactorFail = false, categories = [] } = {}) {
  const calls = { redactor: [], gateway: [] };
  const redactorTransport = async (url, headers, body) => {
    calls.redactor.push({ url, headers, body });
    if (redactorFail) throw new Error('down');
    return { status: 200, headers: {}, json: { text: body.text, categories } };
  };
  const queue = [...replies];
  const gatewayTransport = async (url, headers, body) => {
    calls.gateway.push({ url, headers, body });
    return { status: 200, headers: cost === null ? {} : { 'x-litellm-response-cost': cost },
      json: { model: 'gemini-test', usage: { total_tokens: 120 }, choices: [{ finish_reason: 'stop', message: { content: JSON.stringify(queue.shift()) } }] } };
  };
  return { calls, redactorTransport, gatewayTransport };
}

function guideWith(options) {
  const f = fakes(options);
  const lines = [];
  const stream = { write: (line) => lines.push(JSON.parse(line)) };
  const guide = new Guide({ index: INDEX, stream,
    redactor: new Redactor('k'.repeat(64), { transport: f.redactorTransport }),
    gateway: new Gateway('sk-test', { transport: f.gatewayTransport }) });
  return { guide, lines, ...f };
}

module.exports = { INDEX, guideWith, fakes };
