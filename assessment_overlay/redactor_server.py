#!/usr/bin/env python3
"""Assessment entrypoint: use the mounted platform redactor, adding only durable caps.

The platform's Handler, Server, Capacity, Budget, phone guard, key validation,
policy check and gRPC transport remain the sole implementations of those rules.
"""

import hashlib
import importlib.util
import os
from pathlib import Path
import sys


PLATFORM_SOURCE = Path('/programs/redactor_server.py')
GUARD_SOURCE = Path('/assessment/sdp_guard.py')
ATTEMPTS = '/assessment-state/sdp-attempts.json'
COMPLETIONS = '/assessment-state/sdp-completions.json'


def load_platform(source=PLATFORM_SOURCE):
    """Import the actual mounted platform source; never import this entrypoint."""
    source = Path(source).resolve()
    if source == Path(__file__).resolve():
        raise RuntimeError('assessment redactor cannot replace platform source')
    sys.path.insert(0, str(source.parent))  # platform's sibling phone_guard
    spec = importlib.util.spec_from_file_location('_assessment_platform_redactor', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def configure(platform, guard, *, attempts=ATTEMPTS, completions=COMPLETIONS):
    """Decorate only platform extension points; its HTTP and SDP logic is unchanged."""
    original_client = platform.keepalive_client
    original_budget = platform.Budget
    ledger = guard.CompletedLedger(completions)

    def capped_client():
        return guard.LimitedClient(original_client(), attempts)

    def capped_budget(*args, **kwargs):
        return CompletionBudget(original_budget(*args, **kwargs), ledger)

    platform.keepalive_client = capped_client
    platform.Budget = capped_budget
    return platform


def main():
    platform = configure(load_platform(), load_guard())
    platform.main()


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit('assessment_redactor:arguments_rejected')
    os.umask(0o077)
    main()
