"""Sign-in for the Financial Agent: argon2id password hashes and a signed, expiring session cookie.

- Passwords are verified with argon2id. An unknown user is checked against a dummy hash, so the response time does
  not reveal which usernames exist.
- Failed sign-ins are throttled per username and per client (5 failures in 15 minutes).
- The session cookie is `payload.signature`, where the HMAC-SHA256 key exists only in the agent's Secret. It carries
  the user id, the display name, an expiry (1 hour), a CSRF token and a session id; sign-out revokes the session id.
  The browser never chooses the user: every database call takes the user id from a verified session only.
"""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

HASHER = PasswordHasher()  # argon2id, library defaults (memory-hard)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(16))
SESSION_SECONDS = 3600
MAX_FAILURES, FAILURE_WINDOW = 5, 900


def hash_password(password):
    return HASHER.hash(password)


def verify_password(stored_hash, password):
    """Constant-shape check: always runs one argon2 verification."""
    try:
        return HASHER.verify(stored_hash or DUMMY_HASH, password) and stored_hash is not None
    except (Argon2Error, InvalidHashError):
        return False


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


class Sessions:
    def __init__(self, key, *, clock=time.time):
        if len(key) < 32:
            raise ValueError('session key too short')
        self._key, self._clock = key, clock
        self._revoked, self._lock = {}, threading.Lock()

    def issue(self, user_id, display_name):
        payload = {'u': user_id, 'n': display_name, 'exp': int(self._clock()) + SESSION_SECONDS,
                   'c': secrets.token_urlsafe(24), 'j': secrets.token_urlsafe(12)}
        body = _b64(json.dumps(payload, separators=(',', ':')).encode())
        return body + '.' + _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest()), payload

    def verify(self, cookie):
        try:
            body, signature = cookie.split('.')
            expected = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(_unb64(body))
        except (ValueError, AttributeError):
            return None
        now = self._clock()
        with self._lock:
            self._revoked = {j: e for j, e in self._revoked.items() if e > now}
            if payload.get('j') in self._revoked:
                return None
        return payload if type(payload.get('exp')) is int and payload['exp'] > now else None

    def revoke(self, payload):
        with self._lock:
            self._revoked[payload['j']] = payload['exp']


class LoginThrottle:
    def __init__(self, *, clock=time.time):
        self._failures, self._clock, self._lock = {}, clock, threading.Lock()

    def _recent(self, key):
        now = self._clock()
        self._failures[key] = [t for t in self._failures.get(key, []) if now - t < FAILURE_WINDOW]
        return self._failures[key]

    def blocked(self, *keys):
        with self._lock:
            return any(len(self._recent(k)) >= MAX_FAILURES for k in keys)

    def failed(self, *keys):
        with self._lock:
            for key in keys:
                self._recent(key).append(self._clock())
