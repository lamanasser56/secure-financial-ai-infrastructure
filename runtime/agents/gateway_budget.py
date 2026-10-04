"""Unwired reset-independent attempt budget around the existing gateway seam."""

import threading
import time

from runtime.phase3.trusted_runtime import APPROVED_MODEL_ALIAS, ControlFailure


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
            if (
                not isinstance(subject, str)
                or not 1 <= len(subject) <= 128
                or self._clock() >= self._expires
                or self._used >= self._total
                or self._subjects.get(subject, 0) >= self._per_subject
            ):
                raise ControlFailure("litellm", "attempt_budget")
            self._used += 1
            self._subjects[subject] = self._subjects.get(subject, 0) + 1


class BudgetedGateway:
    """Trusted composition only; does not execute tools or modify policy."""

    def __init__(self, gateway, budget, credential, *, subject, profile):
        credential.value(profile)
        self._gateway, self._budget, self._credential = gateway, budget, credential
        self._subject, self._profile = subject, profile

    @property
    def call_count(self):
        return self._gateway.call_count

    def measurement_snapshot(self):
        return self._gateway.measurement_snapshot()

    def complete(self, model_alias, redacted_text, metadata):
        if model_alias != APPROVED_MODEL_ALIAS:
            raise ControlFailure("litellm", "invalid_configuration")
        self._credential.value(self._profile)
        self._budget.reserve(self._subject)
        return self._gateway.complete(model_alias, redacted_text, metadata)
