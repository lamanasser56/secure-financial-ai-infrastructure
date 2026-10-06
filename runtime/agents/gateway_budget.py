"""Unwired reset-independent attempt budget around the existing gateway seam."""

import threading
import time
import hmac
import os

from runtime.phase3.trusted_runtime import APPROVED_MODEL_ALIAS, ControlFailure
from runtime.phase3.adapters import HttpLiteLLMGateway
from runtime.agents.credentials import FORBIDDEN_APPLICATION_ENVIRONMENTS
from runtime.agents.terminal_diagnostics import BudgetAdmissionFailure


class RunAttemptBudget:
    """One operator run, shared across profiles/conversation resets.

    Failed dispatches consume attempts. No provider-receipt/billing claim and no
    persistence or reset API. Restart/disconnect requires a separately reviewed
    ledger; this in-memory candidate is not durable account enforcement.
    """

    def __init__(
        self, *, total=32, per_subject=16, lifetime=3600, clock=time.monotonic
    ):
        if (
            type(total) is not int
            or not 1 <= total <= 32
            or type(per_subject) is not int
            or not 1 <= per_subject <= 16
            or type(lifetime) not in (int, float)
            or not 0 < lifetime <= 3600
        ):
            raise ValueError("agent:invalid_budget")
        self._total, self._per_subject = total, per_subject
        self._clock, self._expires = clock, clock() + lifetime
        self._used, self._subjects, self._lock = 0, {}, threading.Lock()

    def reserve(self, subject):
        with self._lock:
            if not isinstance(subject, str) or not 1 <= len(subject) <= 128:
                raise ControlFailure('litellm', 'invalid_configuration')
            if self._clock() >= self._expires:
                raise BudgetAdmissionFailure('run_deadline_exceeded')
            if self._used >= self._total:
                raise BudgetAdmissionFailure('total_attempt_budget_exhausted')
            if self._subjects.get(subject, 0) >= self._per_subject:
                raise BudgetAdmissionFailure('subject_attempt_budget_exhausted')
            self._used += 1
            self._subjects[subject] = self._subjects.get(subject, 0) + 1

    def snapshot(self, subject):
        with self._lock:
            return {'total_used':self._used,'total_limit':self._total,
                'subject_used':self._subjects.get(subject,0),'subject_limit':self._per_subject,
                'remaining_seconds':max(0,self._expires-self._clock()),'retries':0}


class BudgetedGateway:
    """Trusted composition only; does not execute tools or modify policy."""

    def __init__(self, gateway, budget, credential, *, subject, profile):
        credential.value(profile)
        self._gateway, self._budget, self._credential = gateway, budget, credential
        self._subject, self._profile = subject, profile
        self._admissions = self._denials = 0

    @property
    def call_count(self):
        return self._gateway.call_count

    def measurement_snapshot(self):
        return self._gateway.measurement_snapshot() | {
            'budget_admissions': self._admissions, 'budget_denials': self._denials,
            'shared_run_budget':self._budget.snapshot(self._subject)}

    def complete(self, model_alias, redacted_text, metadata):
        if model_alias != APPROVED_MODEL_ALIAS:
            raise ControlFailure("litellm", "invalid_configuration")
        try:
            self._credential.value(self._profile)
        except ValueError:
            raise ControlFailure('litellm', 'credential_unavailable') from None
        try:
            self._budget.reserve(self._subject)
        except BudgetAdmissionFailure:
            self._denials += 1
            raise
        self._admissions += 1
        return self._gateway.complete(model_alias, redacted_text, metadata)


class ScopedHTTPGateway(BudgetedGateway):
    """Unwired trusted factory binding the checked handle to the actual HTTP key.

    Rotation requires a new factory with the same run budget after revocation.
    A lifecycle guard for one key cannot authorize an adapter using another key.
    These local guards do not qualify server/database key enforcement.
    """

    def __init__(self, base_url, budget, credential, *, subject, profile, timeout=20):
        if (
            FORBIDDEN_APPLICATION_ENVIRONMENTS & os.environ.keys()
            or not isinstance(subject, str)
            or not 1 <= len(subject) <= 128
            or type(timeout) not in (int, float)
            or not 0 < timeout <= 20
            or not isinstance(budget, RunAttemptBudget)
        ):
            raise ControlFailure("litellm", "invalid_configuration")
        self._bound_key = credential.value(profile)
        gateway = HttpLiteLLMGateway(base_url, timeout, client_key=self._bound_key)
        super().__init__(gateway, budget, credential, subject=subject, profile=profile)

    def complete(self, model_alias, redacted_text, metadata):
        try:
            current = self._credential.value(self._profile)
        except ValueError:
            raise ControlFailure('litellm', 'credential_unavailable') from None
        if not hmac.compare_digest(current, self._bound_key):
            raise ControlFailure("litellm", "invalid_configuration")
        return super().complete(model_alias, redacted_text, metadata)
