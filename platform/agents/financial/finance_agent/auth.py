"""Sign-in for the Financial Agent: argon2id password hashes and a signed, expiring session cookie.

- Passwords are verified with argon2id. An unknown user is checked against a dummy hash, so the response time does
  not reveal which usernames exist.
- Failed sign-ins are throttled per username (5 failures in 15 minutes lock that username only) with a per-client
  backstop (20 failures in 15 minutes). The client is the TCP peer address; X-Forwarded-For is never read.
- The session cookie is `payload.signature`, where the HMAC-SHA256 key exists only in the agent's Secret. It carries
  the user id, the display name, an expiry (1 hour), a CSRF token, a session id and the process's session epoch;
  sign-out revokes the session id. The epoch is new at every start, so a restart (which forgets revocations) also
  invalidates every cookie issued before it.
  The browser never chooses the user: every database call takes the user id from a verified session only.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

HASHER = PasswordHasher()  # argon2id, library defaults (memory-hard)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(16))
SESSION_SECONDS = 3600
MAX_FAILURES, MAX_CLIENT_FAILURES, FAILURE_WINDOW = 5, 20, 900
MAX_TRACKED = 10_000  # throttle keys kept in memory; stale ones are pruned first


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
        self._epoch = secrets.token_urlsafe(12)  # rotated at every start: older cookies stop working
        self._revoked, self._lock = {}, threading.Lock()

    def issue(self, user_id, display_name):
        payload = {'u': user_id, 'n': display_name, 'exp': int(self._clock()) + SESSION_SECONDS,
                   'c': secrets.token_urlsafe(24), 'j': secrets.token_urlsafe(12), 'e': self._epoch}
        body = _b64(json.dumps(payload, separators=(',', ':')).encode())
        return body + '.' + _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest()), payload

    def verify(self, cookie):
        # compare_digest(str, str) rejects non-ASCII input. Reject the wire shape before hashing/comparing;
        # malformed unauthenticated cookies must take the ordinary sign-in-required path.
        if type(cookie) is not str or len(cookie) > 4096 or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}', cookie):
            return None
        try:
            body, signature = cookie.split('.')
            expected = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(_unb64(body))
        except (ValueError, AttributeError):
            return None
        if type(payload) is not dict or not hmac.compare_digest(str(payload.get('e', '')), self._epoch):
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
    """Per-username lockout plus a per-client backstop.

    One username's failures never lock out another username, so a shared address (port-forward makes every client
    127.0.0.1) cannot be used to lock out everyone with 5 tries; the client backstop is 4x higher.
    """

    def __init__(self, *, clock=time.time):
        self._failures, self._clock, self._lock = {}, clock, threading.Lock()

    def _recent(self, key):
        now = self._clock()
        recent = [t for t in self._failures.get(key, []) if now - t < FAILURE_WINDOW]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def blocked(self, username, client):
        with self._lock:
            return (len(self._recent(('user', username))) >= MAX_FAILURES
                    or len(self._recent(('client', client))) >= MAX_CLIENT_FAILURES)

    def failed(self, username, client):
        with self._lock:
            if len(self._failures) > MAX_TRACKED - 2:  # bounded memory: prune stale keys, then the oldest
                for key in list(self._failures):
                    self._recent(key)
                while len(self._failures) > MAX_TRACKED - 2:  # room for this failure's two keys
                    del self._failures[min(self._failures, key=lambda k: self._failures[k][-1])]
            now = self._clock()
            for key in (('user', username), ('client', client)):
                self._failures[key] = self._recent(key) + [now]
