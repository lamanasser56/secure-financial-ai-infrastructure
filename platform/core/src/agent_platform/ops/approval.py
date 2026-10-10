"""One-use owner approvals (Ed25519).

The front door (apps namespace) holds the approver private key and signs only after the owner approves a
specific proposal in the UI. The ops agent holds only the public key, so it cannot approve itself. A token is
bound to request ID, target, action, arguments digest and evidence digest; it is valid for at most 5 minutes,
must be issued after the agent process started (no replay across restarts), and is accepted once.
"""
import base64
import hashlib
import json
import threading
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

MAX_TTL = 300
FIELDS = ('request_id', 'target', 'action', 'args_digest', 'evidence_digest', 'issued_at', 'expires_at', 'approver')


class ApprovalDenied(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def canonical(claims):
    return json.dumps({k: claims[k] for k in FIELDS}, sort_keys=True, separators=(',', ':')).encode()


def args_digest(arguments):
    return hashlib.sha256(json.dumps(arguments, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def unb64(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


class Signer:
    """Front door only."""

    def __init__(self, private_pem, approver='owner', clock=time.time):
        self._key = serialization.load_pem_private_key(private_pem.encode(), password=None)
        if not isinstance(self._key, Ed25519PrivateKey):
            raise ValueError('approval:key_type')
        self._approver, self._clock = approver, clock

    def sign(self, proposal, ttl=MAX_TTL):
        now = int(self._clock())
        claims = {'request_id': proposal['request_id'], 'target': proposal['target'], 'action': proposal['action'],
                  'args_digest': proposal['args_digest'], 'evidence_digest': proposal['evidence_digest'],
                  'issued_at': now, 'expires_at': now + min(int(ttl), MAX_TTL), 'approver': self._approver}
        return b64(canonical(claims)) + '.' + b64(self._key.sign(canonical(claims)))


class Verifier:
    """Ops agent only: verify, bind and consume."""

    def __init__(self, public_pem, clock=time.time):
        self._key = serialization.load_pem_public_key(public_pem.encode())
        if not isinstance(self._key, Ed25519PublicKey):
            raise ValueError('approval:key_type')
        self._clock, self._started = clock, int(clock())
        self._used, self._lock = set(), threading.Lock()

    def consume(self, token, proposal):
        try:
            payload, signature = token.split('.')
            raw = unb64(payload)
            self._key.verify(unb64(signature), raw)
            claims = json.loads(raw)
        except (ValueError, InvalidSignature, TypeError):
            raise ApprovalDenied('SIGNATURE_INVALID') from None
        if set(claims) != set(FIELDS) or canonical(claims) != raw:
            raise ApprovalDenied('CLAIMS_INVALID')
        now = int(self._clock())
        if not (self._started <= claims['issued_at'] <= now < claims['expires_at']) or claims['expires_at'] - claims['issued_at'] > MAX_TTL:
            raise ApprovalDenied('EXPIRED_OR_STALE')
        for field in ('request_id', 'target', 'action', 'args_digest', 'evidence_digest'):
            if claims[field] != proposal[field]:
                raise ApprovalDenied('BINDING_MISMATCH:' + field)
        with self._lock:
            if claims['request_id'] in self._used:
                raise ApprovalDenied('ALREADY_USED')
            self._used.add(claims['request_id'])
        return claims


def generate_keypair():
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public
