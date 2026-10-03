import copy
import unittest

from runtime.agents.demo import make_demo
from runtime.agents.presentation import format_minor_units, present


class PresentationTests(unittest.TestCase):
    def result(self, profile="financial", period="2026-01", scenario=None):
        core, auth = make_demo(profile)
        return core.run(
            auth,
            {
                "agent": profile,
                "message": (
                    "Analyze synthetic expenses."
                    if profile == "financial"
                    else "Diagnose this synthetic infrastructure failure."
                ),
                "period": period,
                "scenario_id": scenario,
            },
        )

    def test_money_uses_integer_currency_scale(self):
        for amount, expected in (
            (24000, "SAR 240.00"),
            (20000, "SAR 200.00"),
            (4000, "SAR 40.00"),
            (1, "SAR 0.01"),
            (99, "SAR 0.99"),
            (101, "SAR 1.01"),
            (0, "SAR 0.00"),
        ):
            self.assertEqual(format_minor_units(amount, "SAR"), expected)
        for amount, currency in ((True, "SAR"), (1.5, "SAR"), (-1, "SAR"), (1, "XXX")):
            with self.assertRaises(ValueError):
                format_minor_units(amount, currency)

    def test_financial_projection_preserves_integers_and_ranks(self):
        result = self.result()
        original = copy.deepcopy(result)
        finance = present(result)["financial"]
        self.assertEqual(result, original)
        self.assertEqual(finance["total"], "SAR 240.00")
        self.assertEqual(finance["total_minor_units"], 24000)
        self.assertEqual(finance["currency_scale"], 2)
        self.assertEqual(finance["expense_count"], 3)
        self.assertEqual(finance["period"], "2026-01")
        self.assertEqual(finance["source_id"], "synthetic-expenses-v1")
        self.assertEqual(
            [
                (c["rank"], c["category"], c["total_minor_units"], c["amount"])
                for c in finance["categories"]
            ],
            [(1, "software", 20000, "SAR 200.00"), (2, "transport", 4000, "SAR 40.00")],
        )

    def test_model_arithmetic_is_never_a_display_amount(self):
        result = self.result()
        result["answer"]["summary"] = "Untrusted claim: total SAR 9999.99"
        self.assertEqual(present(result)["financial"]["total"], "SAR 240.00")

    def test_inconsistent_aggregates_and_sources_fail_closed(self):
        for mutate in (
            lambda r: r["facts"][0]["result"].update(total_minor_units=9999),
            lambda r: r["facts"][0]["result"].update(expense_count=99),
            lambda r: r["facts"][1]["result"].update(period="2026-02"),
            lambda r: r["facts"][1]["result"].update(source_id="other"),
            lambda r: r["facts"][1]["result"]["categories"].reverse(),
        ):
            result = self.result()
            mutate(result)
            with self.assertRaises(ValueError):
                present(result)

    def test_infrastructure_separates_failure_evidence_from_image_context(self):
        result = self.result("infrastructure", None, "docker-config")
        view = present(result)
        self.assertNotIn("financial", view)
        self.assertNotIn("period", view)
        self.assertEqual(
            [item["source_id"] for item in view["supporting_evidence"]],
            result["answer"]["evidence_ids"],
        )
        self.assertEqual(
            view["supplemental_context"]["source_id"], "synthetic-image-v1"
        )
        self.assertIn("no current digest", view["supplemental_context"]["limitations"])
        self.assertEqual(len(view["unverified_points"]), 2)
        self.assertEqual(
            [field["label"] for field in view["diagnosis"]],
            ["Observed failure", "Suspected cause", "Proposed repair"],
        )

    def test_missing_month_has_no_facts_or_calls(self):
        result = self.result(period=None)
        self.assertEqual(result["status"], "clarification_required")
        view = present(result)
        self.assertEqual(set(view), {"usage"})
        self.assertEqual(view["usage"]["simulated_model_requests"], 0)
        self.assertEqual(view["usage"]["tool_dispatch_attempts"], 0)

    def test_unavailable_month_never_displays_inferred_totals(self):
        result = self.result(period="2026-03")
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("facts", result)
        self.assertNotIn("financial", present(result))

    def test_accounting_is_explicitly_simulated_and_unavailable(self):
        usage = present(self.result())["usage"]
        self.assertEqual(usage["simulated_model_requests"], 3)
        self.assertEqual(usage["external_provider_calls"], 0)
        self.assertEqual(usage["tool_dispatch_attempts"], 2)
        self.assertIsNone(usage["token_usage"])
        self.assertIsNone(usage["cost"])
        self.assertIn("Live Presidio detection is unproven", usage["redaction_notice"])


if __name__ == "__main__":
    unittest.main()
