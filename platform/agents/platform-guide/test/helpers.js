'use strict';
const { DocsIndex } = require('../src/search');
const { Guide } = require('../src/agent');
const { Redactor, Gateway } = require('../src/clients');

const INDEX = new DocsIndex({ schema: 1, built_from: 'docs/', chunks: [
  { path: 'docs/architecture.md', heading: 'Network isolation', text: 'Every namespace has a default-deny NetworkPolicy. Agents reach only the redactor and the gateway. The request limit is 20 per hour.' },
  { path: 'docs/agent-developer-guide.md', heading: 'Onboarding', text: 'Run make onboard A=my-agent to validate the manifest. The budget is at most 5.00 dollars per month.' },
  { path: 'docs/security/threat-model.md', heading: 'Secrets', text: 'Keys live in Kubernetes Secrets that are mounted read-only into the pod of the agent that owns them.' },
] });

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

const SEARCH = { action: 'tool', tool: 'docs_search', args: { query: 'network isolation default deny' } };
module.exports = { INDEX, guideWith, fakes, SEARCH };
