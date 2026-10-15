'use strict';
// One request ID per request: 32 lowercase hex characters (the same shape the redactor and the gateway accept).
const crypto = require('node:crypto');

const PATTERN = /^[0-9a-f]{32}$/;
const HEADER = 'X-Request-ID';

function newRequestId() {
  return crypto.randomBytes(16).toString('hex');
}

module.exports = { PATTERN, HEADER, newRequestId };
