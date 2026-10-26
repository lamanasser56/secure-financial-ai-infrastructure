#!/usr/bin/env python3
"""Assessment entrypoint: use the image-owned platform redactor with durable caps.

The platform's Handler, Server, Capacity, Budget, phone guard, key validation,
policy check and gRPC transport remain the sole implementations of those rules.
"""

import hashlib
import importlib.util
import os
from pathlib import Path
import sys


GUARD_SOURCE = Path('/assessment/sdp_guard.py')
ATTEMPTS = '/assessment-state/sdp-attempts.json'
COMPLETIONS = '/assessment-state/sdp-completions.json'


def load_platform():
    """Import the signed image's regular package entrypoint, not an assessment copy."""
    from agent_platform.programs import redactor_server
    return redactor_server


def load_guard(source=GUARD_SOURCE, expected_hash=None):
    """Require the transform's exact guard digest before importing its ledgers."""
    source = Path(source)
    expected_hash = expected_hash or os.environ['ASSESSMENT_GUARD_SHA256']
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected_hash:
        raise RuntimeError('assessment SDP guard integrity')
    spec = importlib.util.spec_from_file_location('_assessment_sdp_guard', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CompletionRedactor:
    """Reserve before SDP, persist completion before platform sends the response."""

    def __init__(self, redactor, ledger):
        self.redactor, self.ledger = redactor, ledger

    def redact(self, text):
        token = self.ledger.reserve()
        try:
            result = self.redactor.redact(text)
        except Exception:
            self.ledger.abort(token)
            raise
        self.ledger.complete(token)
        return result


class CompletionBudget:
    def __init__(self, budget, ledger):
        self.budget, self.ledger = budget, ledger

    def current(self):
        return CompletionRedactor(self.budget.current(), self.ledger)


def main():
    guard = load_guard()
    attempts = guard.Ledger(ATTEMPTS)
    completions = guard.CompletedLedger(COMPLETIONS)
    load_platform().main(
        attempt_hook=lambda _operation: attempts.reserve(),
        budget_wrapper=lambda budget: CompletionBudget(budget, completions))


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit('assessment_redactor:arguments_rejected')
    os.umask(0o077)
    main()
