'use strict';
// The platform clients, written like the Financial Agent's: the redactor first (fail closed), then the gateway with
// this agent's own scoped key. Both calls carry the request ID. No provider, no internet: only these two Services.
const http = require('node:http');
const { identifierSpans, maskSpans } = require('./identifiers');
const { HEADER } = require('./requestId');

const REDACTOR_URL = 'http://redactor.platform.svc.cluster.local:4003/redact';
const GATEWAY_URL = 'http://gateway.platform.svc.cluster.local:4000/v1/chat/completions';
const ALIAS = 'secure-financial-chat';
const SUPPORTED = new Set(['CREDIT_CARD', 'EMAIL_ADDRESS', 'IBAN_CODE', 'PHONE_NUMBER', 'SAUDI_BANK_ACCOUNT', 'SAUDI_NATIONAL_ID',
  'SAUDI_RESIDENT_ID', 'SAUDI_VAT_ID']);
const MAX_TEXT_BYTES = 4096;
const MAX_REPLY_TOKENS = 1024;
const MODEL_NAME = /^[A-Za-z0-9._/:-]{1,80}$/;
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;

class Blocked extends Error {
  constructor(reason) {
    super(reason);
    this.reason = reason;
  }
}

// Default transport: plain HTTP to an in-cluster Service, no proxy, bounded response.
function post(url, headers, body, timeoutMs) {
  return new Promise((resolve, reject) => {
    const data = Buffer.from(JSON.stringify(body));
    const request = http.request(url, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json',
      'Content-Length': data.length }, timeout: timeoutMs }, (response) => {
      const parts = [];
      let size = 0;
      response.on('data', (chunk) => {
        size += chunk.length;
        if (size > 1 << 20) request.destroy(new Error('response_too_large'));
        else parts.push(chunk);
      });
      response.on('end', () => {
        try {
          resolve({ status: response.statusCode, headers: response.headers, json: JSON.parse(Buffer.concat(parts).toString('utf8')) });
        } catch (error) {
          reject(error);
        }
      });
    });
    request.on('timeout', () => request.destroy(new Error('timeout')));
    request.on('error', reject);
    request.end(data);
  });
}

// Deterministic email layer in front of the redactor (the Financial Agent does the same in Python): emails never leave.
function maskEmails(text) {
  let found = false;
  const masked = text.replace(EMAIL, () => {
    found = true;
    return '[EMAIL_ADDRESS]';
  });
  return { masked, found };
}

class Redactor {
  constructor(key, { transport = post, url = REDACTOR_URL, timeoutMs = 8000 } = {}) {
    if (typeof key !== 'string' || key.length !== 64) throw new Error('redaction:invalid_client');
    this.key = key;
    this.transport = transport;
    this.url = url;
    this.timeoutMs = timeoutMs;
  }

  // -> { text, categories }. Any failure throws Blocked('redaction_unavailable'): nothing reaches the model.
  // Emails, then structured identifiers (phone, IBAN, VAT, card, labelled IDs) are masked here, in raw text and inside the
  // JSON prompt alike: the redactor's own patterns for those are line-anchored and never match inside a JSON string.
  async redact(text, requestId) {
    const emailMasked = maskEmails(String(text));
    let spans;
    try {
      spans = identifierSpans(emailMasked.masked);
    } catch {
      throw new Blocked('redaction_unavailable');
    }
    const originals = spans.map(([start, end]) => emailMasked.masked.slice(start, end));
    const masked = maskSpans(emailMasked.masked, spans);
    const found = emailMasked.found;
    if (Buffer.byteLength(masked) > MAX_TEXT_BYTES) throw new Blocked('redaction_unavailable');
    let response;
    try {
      response = await this.transport(this.url, { Authorization: 'Bearer ' + this.key, [HEADER]: requestId }, { text: masked }, this.timeoutMs);
    } catch {
      throw new Blocked('redaction_unavailable');
    }
    const result = response && response.json;
    const categories = result && result.categories;
    const ok = response && response.status === 200 && result && typeof result === 'object'
      && Object.keys(result).sort().join() === 'categories,text' && typeof result.text === 'string'
      && Array.isArray(categories) && categories.every((c) => typeof c === 'string' && SUPPORTED.has(c))
      && categories.join() === [...new Set(categories)].sort().join();
    if (!ok) throw new Blocked('redaction_unavailable');
    if (originals.some((value) => result.text.includes(value))) throw new Blocked('redaction_unavailable'); // fail closed
    const all = new Set(categories);
    if (found) all.add('EMAIL_ADDRESS');
    for (const [, , category] of spans) all.add(category);
    return { text: result.text, categories: [...all].sort() };
  }
}

class Gateway {
  constructor(key, { transport = post, url = GATEWAY_URL, timeoutMs = 8000 } = {}) {
    this.key = key;
    this.transport = transport;
    this.url = url;
    this.timeoutMs = timeoutMs;
  }

  // -> { content, tokens, model, costUsd }
  async complete(messages, requestId) {
    const body = { model: ALIAS, messages, temperature: 0, max_tokens: MAX_REPLY_TOKENS, stream: false,
      response_format: { type: 'json_object' }, metadata: { request_id: requestId, agent: 'platform-guide' } };
    let response;
    try {
      response = await this.transport(this.url, { Authorization: 'Bearer ' + this.key, [HEADER]: requestId }, body, this.timeoutMs);
    } catch {
      throw new Blocked('model_unavailable');
    }
    const data = response && response.status === 200 ? response.json : null;
    const choice = data && Array.isArray(data.choices) ? data.choices[0] : null;
    const content = choice && choice.message && choice.message.content;
    if (!choice || choice.finish_reason !== 'stop' || typeof content !== 'string' || !content.trim()) throw new Blocked('model_reply_incomplete');
    const total = data.usage && data.usage.total_tokens;
    const raw = response.headers && response.headers['x-litellm-response-cost'];
    const cost = typeof raw === 'string' && raw.trim() !== '' ? Number(raw) : NaN;
    return {
      content,
      tokens: Number.isInteger(total) && total > 0 ? total : MAX_REPLY_TOKENS + MAX_TEXT_BYTES * 3, // never charge zero
      model: typeof data.model === 'string' && MODEL_NAME.test(data.model) ? data.model : null,
      costUsd: Number.isFinite(cost) && cost >= 0 && cost < 1000 ? Math.round(cost * 1e6) / 1e6 : null,
    };
  }
}

module.exports = { Redactor, Gateway, Blocked, maskEmails, post, ALIAS, SUPPORTED };
