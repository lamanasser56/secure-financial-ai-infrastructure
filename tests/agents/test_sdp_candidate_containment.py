"""Test-only composition/accounting, never live factory/provider wiring."""

import json
from types import SimpleNamespace
import unittest

from runtime.agents.core import TurnContext
from runtime.agents.demo import make_demo
from runtime.phase3.google_sdp_adapter import (
    ContentAttemptBudget,
    ENDPOINT,
    GoogleSDPRedactor,
)


class PlainFixtureClient:
    """No detector: synthetic no-sensitive-value agent requests only."""

    api_endpoint = ENDPOINT

    def inspect_content(self, *, request, retry, timeout):
        return SimpleNamespace(
            result=SimpleNamespace(findings=[], findings_truncated=False)
        )

    def deidentify_content(self, *, request, retry, timeout):
        return SimpleNamespace(
            item=SimpleNamespace(value=request["item"]["value"]),
            overview=SimpleNamespace(transformed_bytes=0, transformation_summaries=[]),
        )


class SDPCandidateContainmentTests(unittest.TestCase):
    def test_both_profiles_include_prompt_tool_final_and_retained_context_redaction(
        self,
    ):
        for profile, message, expected_models, expected_tools in (
            ("financial", "Show my expenses for January 2026.", 3, 2),
            ("infrastructure", "Explain the docker configuration failure.", 4, 3),
        ):
            core, authorization = make_demo(profile)
            budget = ContentAttemptBudget(174)
            redactor = GoogleSDPRedactor(
                "synthetic-eval", client=PlainFixtureClient(), budget=budget
            )
            core.redactor = redactor
            request = {
                "agent": profile,
                "message": message,
                "period": None,
                "scenario_id": "docker-config" if profile == "infrastructure" else None,
            }
            response = core.run(authorization, request)
            self.assertEqual(response["status"], "completed")
            self.assertEqual(
                (response["model_requests"], response["tool_executions"]),
                (expected_models, expected_tools),
            )
            first_count = redactor.injected_client_counts["inspect_attempted"]
            self.assertGreater(first_count, expected_models)
            second = core.run(
                authorization,
                request,
                context=TurnContext(
                    history=(
                        {"role": "user", "text": "Synthetic previous input."},
                        {"role": "assistant", "text": "Synthetic previous answer."},
                    )
                ),
            )
            self.assertEqual(second["status"], "completed")
            self.assertEqual(
                redactor.injected_client_counts["inspect_attempted"] - first_count,
                first_count + 2,
            )
            self.assertEqual(sum(redactor.operation_counts.values()), 0)
            self.assertEqual(budget.used, sum(redactor.injected_client_counts.values()))
            self.assertEqual(response["mode"], "offline_simulation")

    def test_budget_or_truncation_failure_before_model_stops_tools_and_model(self):
        for truncated in (False, True):
            core, authorization = make_demo("financial")
            client = PlainFixtureClient()
            if truncated:
                client.inspect_content = lambda **kwargs: SimpleNamespace(
                    result=SimpleNamespace(findings=[], findings_truncated=True)
                )
            core.redactor = GoogleSDPRedactor(
                "synthetic-eval",
                client=client,
                budget=ContentAttemptBudget(1 if not truncated else 18),
            )
            response = core.run(
                authorization,
                {
                    "agent": "financial",
                    "message": "Show expenses for January 2026.",
                    "period": None,
                    "scenario_id": None,
                },
            )
            self.assertEqual(response["status"], "blocked")
            self.assertEqual(
                (response["model_requests"], response["tool_executions"]), (0, 0)
            )
            self.assertNotIn("Show expenses", json.dumps(response))

    def test_authoritative_factory_still_constructs_presidio_not_sdp(self):
        from pathlib import Path
        from runtime.agents import demo

        source = Path(demo.__file__).read_text()
        self.assertNotIn("GoogleSDPRedactor", source)
        self.assertIn("BilingualPresidioAnalyzer", source)
