"""Candidate scoped-key contracts; no administration or cloud operations."""

import os
import re
import time

from runtime.agents.controls import PROFILES
from runtime.phase3.trusted_runtime import APPROVED_MODEL_ALIAS

CLIENT_ENVIRONMENTS = {
    "infrastructure": "PORTFOLIO_LITELLM_INFRASTRUCTURE_CLIENT_KEY",
    "financial": "PORTFOLIO_LITELLM_FINANCIAL_CLIENT_KEY",
}
FORBIDDEN_APPLICATION_ENVIRONMENTS = frozenset(
    {
        "PORTFOLIO_LITELLM_MASTER_KEY",
        "LITELLM_MASTER_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "VERTEXAI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AZURE_API_KEY",
    }
)


def application_client_key(profile):
    """Read only scoped startup secrets; reject an administrative environment.

    This cannot prove filesystem/process isolation. Mount/identity denial is an
    independent deployment gate; no provider SDK or ADC is consulted here.
    """
    if (
        profile not in PROFILES
        or FORBIDDEN_APPLICATION_ENVIRONMENTS & os.environ.keys()
    ):
        raise ValueError("agent:invalid_live_integration")
    key = os.environ.get(CLIENT_ENVIRONMENTS[profile])
    if (
        not isinstance(key, str)
        or not 16 <= len(key) <= 512
        or not re.fullmatch(r"[A-Za-z0-9_-]+", key)
    ):
        raise ValueError("agent:invalid_live_integration")
    return key


def issuance_request(profile, owner_id):
    """Operator-only request shape, not issuance or proof of gateway enforcement.

    The owner must be a non-administrator, separately verified at the gateway.
    No key value is returned, generated or persisted by this function.
    """
    if profile not in PROFILES or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", owner_id):
        raise ValueError("credential:invalid_scope")
    return {
        "user_id": owner_id,
        "models": [APPROVED_MODEL_ALIAS],
        "duration": "1h",
        "allowed_routes": ["/chat/completions"],
        "rpm_limit": 4,
        "tpm_limit": 8192,
        "max_budget": 0.5,
        "metadata": {"agent_profile": profile},
    }


class ScopedCredential:
    """Ephemeral candidate application-side expiry/revocation guard.

    Local revocation does not revoke the server key. Operator gateway deletion
    and independent denial verification remain mandatory, including after crashes.
    """

    def __init__(self, profile, value, expires_at, *, clock=time.time):
        if (
            profile not in PROFILES
            or type(value) is not str
            or not re.fullmatch(r"[A-Za-z0-9_-]{16,512}", value)
            or type(expires_at) not in (int, float)
            or not clock() < expires_at <= clock() + 3600
        ):
            raise ValueError("credential:invalid_scope")
        self._profile, self._value, self._expires, self._clock = (
            profile,
            value,
            expires_at,
            clock,
        )

    def __repr__(self):
        return "ScopedCredential(<private>)"

    def value(self, profile):
        if (
            self._value is None
            or profile != self._profile
            or self._clock() >= self._expires
        ):
            raise ValueError("credential:unavailable")
        return self._value

    def revoke(self):
        self._value = None

    def rotate(self, replacement):
        # Revoke first. A malformed replacement leaves this handle unusable.
        self.revoke()
        if (
            not isinstance(replacement, ScopedCredential)
            or replacement._profile != self._profile
        ):
            raise ValueError("credential:invalid_scope")
        replacement.value(self._profile)
        return replacement
