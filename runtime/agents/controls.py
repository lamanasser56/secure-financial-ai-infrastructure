"""Trusted startup identity, assessment and POSIX operation deadlines."""

from contextlib import contextmanager
import hashlib
import hmac
import json
import re
import secrets
import signal
import threading

from runtime.phase3.trusted_runtime import ControlFailure, IdentityClaims, TenantContext
from runtime.phase4.prompt_injection import (
    PromptInjectionAssessment,
    PromptInjectionOutcome,
)

PROFILES = {
    "infrastructure": frozenset(
        {"read_ci_summary", "read_image_summary", "read_runbook_section"}
    ),
    "financial": frozenset({"expense_summary", "expense_categories"}),
}
DEMO_USERS = {"demo-alpha": "fixture-a", "demo-beta": "fixture-b"}


class DemoIdentity:
    """Simulated authentication only; chosen by the server/CLI startup operator.

    Browser data never selects the identity, claims, tenant or capabilities.
    A separately integrated real authenticator/resolver/authorizer is needed
    for live service use. No simulated credential grants production access.
    """

    simulated = True

    def __init__(self, user, actions, key=None):
        if user not in DEMO_USERS:
            raise ValueError("identity:invalid_demo_user")
        self._claims = IdentityClaims(
            user, DEMO_USERS[user], frozenset(actions) | {"chat.complete"}
        )
        self._token = "Bearer " + secrets.token_urlsafe(32)
        key = key if key is not None else secrets.token_bytes(32)
        self._tenant = TenantContext(
            DEMO_USERS[user],
            hmac.new(key, DEMO_USERS[user].encode(), hashlib.sha256).hexdigest()[:16],
        )

    def authenticate(self, authorization):
        if not isinstance(authorization, str) or not hmac.compare_digest(
            authorization, self._token
        ):
            raise ControlFailure("authentication", "invalid_token")
        return self._claims

    def resolve(self, claims):
        if claims != self._claims:
            raise ControlFailure("tenant_context", "malformed_context")
        return self._tenant

    def authorize(self, claims, tenant, action):
        return (
            claims == self._claims
            and tenant == self._tenant
            and action in claims.scopes
        )

    def startup_authorization(self):
        return self._token


class BoundedInjectionAssessor:
    """Illustrative indicators plus enforced capability/schema containment.

    Pattern matching cannot establish complete prompt-injection detection.
    The read-only allowlist is enforced independently of this assessment.
    """

    def assess(self, arguments):
        text = json.dumps(arguments, ensure_ascii=False).lower()
        indicators = []
        for category, pattern in (
            (
                "instruction_override",
                r"ignore (?:all |previous )?instructions|تجاهل التعليمات|(?:use|set|override|change) (?:the )?(?:gateway|endpoint|model|credentials)|(?:غير|غيّر|استخدم) (?:المزود|النموذج|نقطة الاتصال|بيانات الاعتماد)",
            ),
            (
                "policy_evasion",
                r"bypass (?:policy|redaction)|disable presidio|تجاوز السياسة",
            ),
            ("tool_manipulation", r"execute shell|run kubectl|terraform apply"),
            (
                "data_exfiltration",
                r"send credentials|another tenant|tenant[_ -]?id|other tenant|show (?:the )?(?:credentials|private key)|مستأجر آخر|مستاجر اخر|ارسل بيانات الاعتماد|أرسل بيانات الاعتماد",
            ),
        ):
            if re.search(pattern, text):
                indicators.append(category)
        return PromptInjectionAssessment(
            (
                PromptInjectionOutcome.SUSPECTED
                if indicators
                else PromptInjectionOutcome.CLEAR
            ),
            tuple(indicators),
        )


class NoWriteApproval:
    def retrieve_verified(self, approval_id):
        raise ControlFailure("human_approval_verification", "missing_decision")


class DeadlineExceeded(BaseException):
    """Not swallowed by adapter exception normalization; no background work."""


@contextmanager
def deadline(seconds):
    if threading.current_thread() is not threading.main_thread() or not hasattr(
        signal, "setitimer"
    ):
        raise ControlFailure("agent", "deadline_unavailable")
    previous = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    if previous_timer != (0.0, 0.0):
        raise ControlFailure("agent", "deadline_unavailable")

    def expired(signum, frame):
        raise DeadlineExceeded()

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
