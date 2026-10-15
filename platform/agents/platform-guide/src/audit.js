'use strict';
// One JSON line on stdout per event, the same shape as the platform's audit lines (agent_platform/audit.py).
// Callers pass only bounded, non-content fields; these names are refused outright.
const FORBIDDEN = new Set(['text', 'prompt', 'content', 'token', 'key', 'secret', 'password', 'authorization', 'question', 'answer']);

function emit(event, component, fields, stream = process.stdout) {
  for (const name of Object.keys(fields)) {
    if (FORBIDDEN.has(name)) throw new Error('audit:content_field_rejected');
  }
  const line = { audit_event: event, component, at: Math.round(Date.now()) / 1000, ...fields };
  const sorted = Object.fromEntries(Object.entries(line).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
  stream.write(JSON.stringify(sorted) + '\n');
}

module.exports = { emit, FORBIDDEN };
