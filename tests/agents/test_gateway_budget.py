"""Candidate run limits survive wrapper/conversation resets and failures."""

import unittest
from unittest import mock

from runtime.agents.credentials import ScopedCredential
from runtime.agents.gateway_budget import (
    BudgetedGateway,
    RunAttemptBudget,
    ScopedHTTPGateway,
)
from runtime.phase3.trusted_runtime import ControlFailure

PROMPT = '{"agent":"financial","observations":[],"period":"2026-01"}'


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

    def test_scoped_http_factory_uses_exact_handle_and_measured_loopback_requests(self):
        from test_live_preparation import boundary_fixture

        with boundary_fixture() as (url, records), mock.patch.dict(
            "os.environ", {}, clear=True
        ):
            credential = self.credential()
            gateway = ScopedHTTPGateway(
                url,
                RunAttemptBudget(total=1),
                credential,
                subject="verified-subject",
                profile="financial",
                timeout=1,
            )
            gateway.complete("secure-financial-chat", PROMPT, {})
            self.assertEqual(
                gateway._gateway._authorization, "Bearer invalid-fixture-key-only"
            )
            self.assertEqual(gateway.call_count, 1)
            self.assertEqual(len(records), 1)
            credential.revoke()
            with self.assertRaises(ValueError):
                gateway.complete("secure-financial-chat", "redacted fixture", {})
            self.assertEqual(len(records), 1)

    def test_rotation_retains_budget_and_static_credential_mismatch_denies_before_http(
        self,
    ):
        from test_live_preparation import boundary_fixture

        with boundary_fixture() as (url, records), mock.patch.dict(
            "os.environ", {}, clear=True
        ):
            budget = RunAttemptBudget(total=1)
            old = self.credential()
            gateway = ScopedHTTPGateway(
                url, budget, old, subject="subject", profile="financial", timeout=1
            )
            gateway.complete("secure-financial-chat", PROMPT, {})
            replacement = old.rotate(
                ScopedCredential(
                    "financial", "invalid-new-fixture-key-only", 200, clock=lambda: 100
                )
            )
            with self.assertRaises(ValueError):
                gateway.complete("secure-financial-chat", "redacted fixture", {})
            rotated = ScopedHTTPGateway(
                url,
                budget,
                replacement,
                subject="subject",
                profile="financial",
                timeout=1,
            )
            with self.assertRaises(ControlFailure):
                rotated.complete("secure-financial-chat", "redacted fixture", {})
            replacement._value = "invalid-unexpected-fixture-key"
            with self.assertRaises(ControlFailure):
                rotated.complete("secure-financial-chat", "redacted fixture", {})
            self.assertEqual(len(records), 1)

    def test_factory_rejects_administrative_environment_and_unbounded_timeout(self):
        with mock.patch.dict(
            "os.environ",
            {"PORTFOLIO_LITELLM_MASTER_KEY": "invalid-fixture-only"},
            clear=True,
        ):
            with self.assertRaises(ControlFailure):
                ScopedHTTPGateway(
                    "http://127.0.0.1:4000",
                    RunAttemptBudget(),
                    self.credential(),
                    subject="subject",
                    profile="financial",
                )
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ControlFailure):
                ScopedHTTPGateway(
                    "http://127.0.0.1:4000",
                    RunAttemptBudget(),
                    self.credential(),
                    subject="subject",
                    profile="financial",
                    timeout=21,
                )
