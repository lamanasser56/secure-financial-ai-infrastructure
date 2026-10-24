"""Trusted frontdoor-issued, active per-turn user capabilities. Never issued by an agent worker."""
import base64
import json
import threading
import time
import uuid

from cryptography.hazmat.primitives import serialization
from agent_platform.boundary_http import Rejected, decode

TOOLS = ('monthly_total', 'spending_by_category', 'find_transactions')
FIELDS = {'purpose', 'user', 'agent', 'nonce', 'issued', 'expires', 'tools'}


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def unb64(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


class CapabilityVerifier:
    def __init__(self, public_pem, *, clock=time.time):
        self.key = serialization.load_pem_public_key(public_pem.encode())
        self.clock = clock

    def verify(self, token, agent):
        try:
            if type(token) is not str or not token.isascii() or len(token) > 2048:
                raise ValueError('token')
            body, signature = token.split('.')
            raw = unb64(body)
            self.key.verify(unb64(signature), raw)
            claims = decode(raw)
            if (type(claims) is not dict or set(claims) != FIELDS or canonical(claims) != raw
                    or claims['purpose'] != 'finance-read' or claims['agent'] != agent
                    or str(uuid.UUID(claims['user'])) != claims['user']
                    or str(uuid.UUID(claims['nonce'])) != claims['nonce']
                    or type(claims['issued']) is not int or type(claims['expires']) is not int
                    or not claims['issued'] <= self.clock() < claims['expires'] <= claims['issued'] + 60
                    or claims['tools'] != list(TOOLS)):
                raise ValueError('claims')
            return claims
        except Exception:
            raise Rejected('CAPABILITY_REJECTED') from None


class CapabilityIssuer(CapabilityVerifier):
    def __init__(self, private_pem, public_pem, *, clock=time.time):
        super().__init__(public_pem, clock=clock)
        self.private = serialization.load_pem_private_key(private_pem.encode(), password=None)
        self.active, self.lock = {}, threading.Lock()

    def issue(self, user, agent):
        claims = {'purpose': 'finance-read', 'user': str(uuid.UUID(user)), 'agent': agent, 'nonce': str(uuid.uuid4()),
                  'issued': int(self.clock()), 'expires': int(self.clock()) + 60, 'tools': list(TOOLS)}
        raw = canonical(claims)
        with self.lock:
            self.active = {n: c for n, c in self.active.items() if c['expires'] > self.clock()}
            if len(self.active) >= 128:
                raise Rejected('CAPABILITY_CAPACITY', 503)
            self.active[claims['nonce']] = claims
        return b64(raw) + '.' + b64(self.private.sign(raw)), claims

    def verify(self, token, agent):
        claims = super().verify(token, agent)
        with self.lock:
            if self.active.get(claims['nonce']) != claims:
                raise Rejected('CAPABILITY_REVOKED')
        return claims

    def revoke(self, claims):
        with self.lock:
            self.active.pop(claims['nonce'], None)
