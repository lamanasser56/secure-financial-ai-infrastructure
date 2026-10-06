"""AM-R4 wiring of the deterministic email layer into the admitted live trial path.

All transport is mocked locally; nothing here is provider evidence.
"""
import time
from types import SimpleNamespace as NS
import unittest
from unittest import mock

from runtime.agents import trial_composition as tc
from runtime.agents.composition import BoundaryBudget, SharedSimulatedRedactor
from runtime.agents.core import AgentCore
from runtime.phase3.deterministic_email import DeterministicEmailRedactor
from runtime.phase3.trusted_runtime import ControlFailure, redact_checked


class LiveRedactionPath(unittest.TestCase):
    def remote(self):
        ledger = mock.Mock()
        return tc.RemoteRedactor("a" * 64, ledger), ledger

    def test_remote_provider_receives_only_masked_text(self):
        remote, ledger = self.remote()
        posted = []
        def post(url, body, timeout, headers):
            posted.append(body["text"])
            return {"text": body["text"].replace("0000000000", "SAUDI_NATIONAL_ID"), "categories": ["SAUDI_NATIONAL_ID"]}
        text = "Email: fixture@example.invalid; amount: SAR 240.00\nNational ID: 0000000000"
        with mock.patch("runtime.agents.trial_composition._post_json", side_effect=post):
            result = redact_checked(DeterministicEmailRedactor(remote), text)
        self.assertEqual(posted, ["Email: EMAIL_ADDRESS; amount: SAR 240.00\nNational ID: 0000000000"])
        self.assertEqual(result.text, "Email: EMAIL_ADDRESS; amount: SAR 240.00\nNational ID: SAUDI_NATIONAL_ID")
        self.assertEqual(result.categories, ("EMAIL_ADDRESS", "SAUDI_NATIONAL_ID"))
        reserved = [c.args for c in ledger.reserve.call_args_list]
        self.assertEqual(reserved[0], ("redaction_input",))  # ledger accounts the masked bytes actually sent
        self.assertEqual(ledger.reserve.call_args_list[0].kwargs["amount"], len(posted[0].encode()))

    def test_provider_echoing_an_address_fails_closed(self):
        remote, _ = self.remote()
        with mock.patch("runtime.agents.trial_composition._post_json", return_value={"text": "fixture@example.com", "categories": []}):
            with self.assertRaises(ControlFailure) as caught:
                DeterministicEmailRedactor(remote).redact("Contact fixture@example.com")
        self.assertEqual(caught.exception.category, "incomplete_redaction")

    def test_budget_passthrough_is_the_delegate_budget(self):
        remote, _ = self.remote()
        wrapper = DeterministicEmailRedactor(remote)
        self.assertIs(wrapper.budget, remote.budget)
        self.assertIs(wrapper.delegate, remote)
        self.assertFalse(wrapper.offline_simulation)
        with self.assertRaises(ValueError):
            DeterministicEmailRedactor(wrapper)

    def test_live_guard_still_rejects_wrapped_simulated_redaction(self):
        wrapped = DeterministicEmailRedactor(SharedSimulatedRedactor(BoundaryBudget()))
        with self.assertRaisesRegex(ValueError, "synthetic_redaction_not_live"):
            AgentCore("financial", NS(), NS(), NS(), wrapped, NS(), simulation=False)

    def test_compose_trial_wires_wrapper_into_every_core_and_gateway(self):
        now = time.time()
        config = {"mode": "admitted_synthetic_trial", "gateway_url": tc.GATEWAY, "subject": "local-fixture-alpha",
                  "expires_at": now + 60, "redactor_key": "a" * 64, "certificates": {}, "tenant": "fixture-a",
                  "tenant_reference_key": "00" * 32, "client_keys": {"financial": "sk-f", "infrastructure": "sk-i"},
                  "tenant_directory": {}, "token": "t"}
        admission = {"scope": "fixed_inputs_qualification", "owner_approved": True, "synthetic_only": True,
                     "subject": "local-fixture-alpha", "expires_at": now + 90}
        ledger = NS(expires=now + 120, model_limit=16, subject_limit=8)
        with mock.patch.object(tc, "TrustedJWTIdentity"), mock.patch.object(tc, "ScopedCredential"), \
                mock.patch.object(tc, "TrialTools"), mock.patch.object(tc, "DurableModelBudget"), \
                mock.patch.object(tc, "TrialGateway") as gateway, mock.patch.object(tc, "IntegratedCore") as core:
            agents, _, redactor = tc.compose_trial(config, admission=admission, ledger=ledger, terminal=None,
                                                   tools_audit=None, connect=lambda: None)
        self.assertIsInstance(redactor, DeterministicEmailRedactor)
        self.assertIsInstance(redactor.delegate, tc.RemoteRedactor)
        self.assertEqual(set(agents), {"financial", "infrastructure"})
        self.assertTrue(all(call.kwargs["redactor"] is redactor for call in gateway.call_args_list))
        self.assertTrue(all(call.args[4] is redactor for call in core.call_args_list))


if __name__ == "__main__":
    unittest.main()
