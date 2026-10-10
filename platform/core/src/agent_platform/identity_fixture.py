"""Synthetic fixture identity issuer (server-selected identity; not a production login).

RS256 tokens in exactly the shape the agent core's TrustedJWTIdentity verifies. The issuer key lives only in the
front door's Secret; tokens live at most one hour and are re-minted by the front door.
"""
import base64
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ISSUER, AUDIENCE, KEY_ID = 'https://fixture-issuer.invalid', 'portfolio-local-composition', 'platform-fixture'


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def generate():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


def mint(private_pem, *, subject, tenant, issued_at, expires_at):
    if not 0 < expires_at - issued_at <= 3600:
        raise ValueError('identity:token_lifetime')
    key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    header = _b64(json.dumps({'alg': 'RS256', 'typ': 'JWT', 'kid': KEY_ID}, separators=(',', ':')).encode())
    payload = _b64(json.dumps({'iss': ISSUER, 'aud': AUDIENCE, 'sub': subject, 'tenant': tenant,
                               'iat': int(issued_at), 'exp': int(expires_at)}, separators=(',', ':')).encode())
    signature = key.sign((header + '.' + payload).encode(), padding.PKCS1v15(), hashes.SHA256())
    return header + '.' + payload + '.' + _b64(signature)
