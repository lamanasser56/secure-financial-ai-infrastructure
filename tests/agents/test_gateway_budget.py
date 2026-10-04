"""Candidate run limits survive wrapper/conversation resets and failures."""

import unittest
from unittest import mock

from runtime.agents.credentials import ScopedCredential
from runtime.agents.gateway_budget import BudgetedGateway, RunAttemptBudget
from runtime.phase3.trusted_runtime import ControlFailure


class BudgetTests(unittest.TestCase):
    def credential(self, profile="financial", clock=lambda: 100):
        return ScopedCredential(profile, "invalid-fixture-key-only", 200, clock=clock)

    def test_failed_attempts_exhaust_shared_identity_across_profiles_and_reset(self):
        gateway = mock.Mock()
        gateway.complete.side_effect = TimeoutError()
        budget = RunAttemptBudget(total=3, per_subject=2)
        for profile in ("financial", "infrastructure"):
            wrapper = BudgetedGateway(
                gateway,
                budget,
                self.credential(profile),
                subject="verified-subject",
                profile=profile,
            )
            with self.assertRaises(TimeoutError):
                wrapper.complete("secure-financial-chat", "redacted fixture", {})
        reset_wrapper = BudgetedGateway(
            gateway,
            budget,
            self.credential(),
            subject="verified-subject",
            profile="financial",
        )
        with self.assertRaises(ControlFailure):
            reset_wrapper.complete("secure-financial-chat", "redacted fixture", {})
        self.assertEqual(gateway.complete.call_count, 2)

    def test_global_run_budget_applies_across_subjects(self):
        gateway = mock.Mock()
        budget = RunAttemptBudget(total=1)
        for subject in ("subject-a", "subject-b"):
            wrapper = BudgetedGateway(
                gateway, budget, self.credential(), subject=subject, profile="financial"
            )
            if subject == "subject-a":
                wrapper.complete("secure-financial-chat", "redacted", {})
            else:
                with self.assertRaises(ControlFailure):
                    wrapper.complete("secure-financial-chat", "redacted", {})
        self.assertEqual(gateway.complete.call_count, 1)

    def test_expired_or_revoked_credentials_and_wrong_model_never_dispatch(self):
        gateway = mock.Mock()
        credential = self.credential()
        wrapper = BudgetedGateway(
            gateway,
            RunAttemptBudget(),
            credential,
            subject="subject",
            profile="financial",
        )
        with self.assertRaises(ControlFailure):
            wrapper.complete("request-selected-model", "redacted", {})
        credential.revoke()
        with self.assertRaises(ValueError):
            wrapper.complete("secure-financial-chat", "redacted", {})
        gateway.complete.assert_not_called()

    def test_expired_run_and_unmeasured_receipts_are_not_reset_or_fabricated(self):
        clock = mock.Mock(return_value=10)
        budget = RunAttemptBudget(lifetime=1, clock=clock)
        clock.return_value = 11
        with self.assertRaises(ControlFailure):
            budget.reserve("subject")
        gateway = mock.Mock()
        gateway.measurement_snapshot.return_value = {
            "http_attempts": 1,
            "usage_unavailable": 1,
        }
        wrapper = BudgetedGateway(
            gateway,
            RunAttemptBudget(),
            self.credential(),
            subject="subject",
            profile="financial",
        )
        self.assertEqual(
            wrapper.measurement_snapshot(), {"http_attempts": 1, "usage_unavailable": 1}
        )
        self.assertNotIn("cost", wrapper.measurement_snapshot())
