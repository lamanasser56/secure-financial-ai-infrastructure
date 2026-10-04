"""Candidate JWT adapter for the existing runtime identity interfaces.

No login server, credential acquisition, network discovery or new policy engine.
An operator-reviewed issuer, public-key snapshot and subject grants are required.
This is not selected by the offline UI or by a production composition.
"""

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import time
from urllib.parse import urlsplit

from runtime.agents.controls import PROFILES
from runtime.agents.schemas import ROOT
from runtime.phase3.trusted_runtime import ControlFailure, IdentityClaims, TenantContext
from runtime.phase4.tool_registry import load_registry


@dataclass(frozen=True)
class SubjectGrant:
    tenant_id: str
    profiles: frozenset[str]


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def _segment(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("encoding")
    return json.loads(
        base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)),
        object_pairs_hook=_unique,
    )


class TrustedJWTIdentity:
    """Verify signatures with locked google-auth, map authority server-side.

    Public keys are refreshed out of band; stale snapshots fail closed. The
    server grants profile capabilities, never token-provided scopes or tenants.
    Google application/default credentials are neither read nor accepted here.
    """

    simulated = False

    def __init__(
        self,
        profile,
        *,
        issuer,
        audience,
        certificates,
        snapshot_expires_at,
        subjects,
        tenant_reference_key,
        clock=time.time,
    ):
        url = urlsplit(issuer)
        if (
            profile not in PROFILES
            or url.scheme != "https"
            or not url.hostname
            or url.query
            or url.fragment
            or url.username
            or url.password
            or not isinstance(audience, str)
            or not 1 <= len(audience) <= 256
            or not isinstance(certificates, dict)
            or not 1 <= len(certificates) <= 8
            or any(
                not isinstance(k, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", k)
                or not isinstance(v, str)
                or not 32 <= len(v) <= 8192
                or "PRIVATE KEY" in v
                for k, v in certificates.items()
            )
            or type(snapshot_expires_at) not in (int, float)
            or not clock() < snapshot_expires_at <= clock() + 86400
            or type(tenant_reference_key) is not bytes
            or len(tenant_reference_key) < 32
            or not isinstance(subjects, dict)
            or not 1 <= len(subjects) <= 128
        ):
            raise ValueError("identity:invalid_trust_configuration")
        for subject, grant in subjects.items():
            if (
                not isinstance(subject, str)
                or not re.fullmatch(r"[A-Za-z0-9._:@-]{1,128}", subject)
                or not isinstance(grant, SubjectGrant)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", grant.tenant_id)
                or type(grant.profiles) is not frozenset
                or not grant.profiles
                or not grant.profiles <= PROFILES.keys()
            ):
                raise ValueError("identity:invalid_trust_configuration")
        from google.auth import jwt

        self._decode = jwt.decode
        self._profile, self._issuer, self._audience = profile, issuer, audience
        self._certificates, self._subjects = dict(certificates), dict(subjects)
        self._expires, self._key, self._clock = (
            snapshot_expires_at,
            tenant_reference_key,
            clock,
        )
        registry = load_registry(ROOT / "contracts/agents/tool-registry.json")
        self._actions = frozenset(
            {"chat.complete", "agent.execute"}
            | {registry[t].authorization.required_action for t in PROFILES[profile]}
        )

    def _claims(self, subject):
        grant = self._subjects.get(subject)
        if grant is None or self._profile not in grant.profiles:
            raise ValueError("subject")
        return IdentityClaims(subject, grant.tenant_id, self._actions)

    def authenticate(self, authorization):
        valid = None
        try:
            if (
                not isinstance(authorization, str)
                or not authorization.startswith("Bearer ")
                or not 1 <= len(authorization) <= 8192
                or self._clock() >= self._expires
            ):
                raise ValueError("token")
            token = authorization[7:]
            header, payload, signature = token.split(".")
            header, payload = _segment(header), _segment(payload)
            if (
                not isinstance(header, dict)
                or not isinstance(payload, dict)
                or set(header) != {"alg", "typ", "kid"}
                or header["alg"] != "RS256"
                or header["typ"] != "JWT"
                or header["kid"] not in self._certificates
                or not re.fullmatch(r"[A-Za-z0-9_-]+", signature)
                or payload.get("iss") != self._issuer
                or payload.get("aud") != self._audience
                or any(type(payload.get(k)) is not int for k in ("iat", "exp"))
                or not 0 < payload["exp"] - payload["iat"] <= 3600
                or not payload["iat"] <= self._clock() < payload["exp"]
                or (
                    "nbf" in payload
                    and (
                        type(payload["nbf"]) is not int
                        or payload["nbf"] > self._clock()
                    )
                )
            ):
                raise ValueError("claims")
            verified = self._decode(
                token,
                certs=self._certificates,
                verify=True,
                audience=self._audience,
                clock_skew_in_seconds=0,
            )
            valid = self._claims(verified.get("sub"))
            if "tenant" in verified and verified["tenant"] != valid.tenant_claim:
                raise ValueError("tenant")
        except Exception:
            valid = None
        if valid is None:
            # Raise outside the handler: no token/library exception context retained.
            raise ControlFailure("authentication", "invalid_token")
        return valid

    def resolve(self, claims):
        try:
            if self._clock() >= self._expires or claims != self._claims(claims.subject):
                raise ValueError("claims")
            reference = hmac.new(
                self._key,
                b"agent-tenant:" + claims.tenant_claim.encode(),
                hashlib.sha256,
            ).hexdigest()[:16]
            return TenantContext(claims.tenant_claim, reference)
        except Exception:
            pass
        raise ControlFailure("tenant_context", "malformed_context")

    def authorize(self, claims, tenant, action):
        try:
            return tenant == self.resolve(claims) and action in self._actions
        except ControlFailure:
            return False
