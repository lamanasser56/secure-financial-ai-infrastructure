"""Offline candidate contracts; SDK messages do not prove Google detection."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from runtime.phase3 import google_sdp_adapter as base
from runtime.phase3.sdp_context_policy import (
    DIRECTORY,
    GoogleSDPContextRedactor,
    load_policy,
    reference_spans,
)
from test_google_sdp_adapter import FakeClient, finding, inspection, output


class ContextPolicyTests(unittest.TestCase):
    def test_all_canonical_labels_bounded_case_spacing_and_punctuation(self):
        groups = {
            "NATIONAL_ID": [
                "National ID",
                "ID number",
                "هوية",
                "رقم الهوية",
                "الهوية الوطنية",
                "العوية",
            ],
            "RESIDENT_ID": [
                "Iqama",
                "residency number",
                "إقامة",
                "اقامة",
                "رقم الإقامة",
                "رقم الاقامة",
                "هوية مقيم",
            ],
            "IBAN_CONTEXT": ["IBAN", "آيبان", "ايبان"],
            "BANK_ACCOUNT": [
                "bank account",
                "bank account number",
                "رقم الحساب",
                "الحساب البنكي",
            ],
            "VAT_ID": ["VAT number", "tax ID", "الرقم الضريبي", "رقم ضريبي"],
            "PHONE_CONTEXT": ["phone number", "رقم الهاتف", "هاتف"],
            "CARD_CONTEXT": ["card number", "رقم البطاقة"],
        }
        for name, labels in groups.items():
            for label in labels:
                for variant in (
                    label,
                    label.lower(),
                    label.upper(),
                    label.replace(" ", "  "),
                    label.replace(" ", "\t"),
                ):
                    for separator in (": ", "： ", " = ", " ", "\n"):
                        value = (
                            "4242424242424242"
                            if name == "CARD_CONTEXT"
                            else "٠٠٠٠٠٠٠٠٠٠"
                        )
                        text = variant + separator + value
                        with self.subTest(category=name):
                            self.assertEqual(
                                reference_spans(text),
                                [
                                    (
                                        len(variant + separator),
                                        len(text),
                                        "PORTFOLIO_" + name,
                                    )
                                ],
                            )
        for label in (
            "National I.D.",
            "رقم\u200cالهوية",
            "National    ID",
            "العويه",
            "الإقامه",
            "إيبان",
            "رقم-الحساب",
            "VAT-number",
        ):
            self.assertEqual(reference_spans(label + ": 0000000000"), [])

    def test_all_frozen_cases_have_independent_exact_expected_spans(self):
        corpus = json.loads((DIRECTORY / "corpus.json").read_text())
        self.assertEqual(len(corpus["cases"]), 86)
        for case in corpus["cases"]:
            with self.subTest(case_id=case["case_id"]):
                expected = [
                    (v["start"], v["end"], v["info_type"])
                    for v in case["expected_spans"]
                ]
                # Failure messages never contain values or raw fixture text.
                self.assertEqual(reference_spans(case["text"]), expected)

    def client(self, text):
        spans = reference_spans(text)
        findings = []
        pieces, cursor = [], 0
        for start, end, name in spans:
            f = finding(text, text[start:end], name)
            f.location.codepoint_range = NS(start=start, end=end)
            f.location.byte_range = NS(
                start=len(text[:start].encode()), end=len(text[:end].encode())
            )
            findings.append(f)
            pieces.extend((text[cursor:start], name))
            cursor = end
        pieces.append(text[cursor:])
        return FakeClient(
            inspect=inspection(findings),
            deidentify=output("".join(pieces), findings, text),
        )

    def test_multifield_unicode_neutral_categories_exact_preservation(self):
        text = (
            "🧪 e\u0301\nNational ID: 0000000000\nإقامة: ٠٠٠٠٠٠٠٠٠٠\nVAT number: 000000000000000\nbank account: 0000000000000000\nIBAN: SA00"
            + "0" * 20
            + "\namount: SAR 240.00\ndate: 2026-01-31\ntenant_ref: 0123456789abcdef"
        )
        client = self.client(text)
        validated_spans = base.inspection_spans(
            client.inspect_result, text, load_policy()["mapping"]
        )
        self.assertEqual(
            {s.category for s in validated_spans},
            {
                "SAUDI_NATIONAL_ID",
                "SAUDI_RESIDENT_ID",
                "SAUDI_VAT_ID",
                "SAUDI_BANK_ACCOUNT",
                "IBAN_CODE",
            },
        )
        redactor = GoogleSDPContextRedactor("synthetic-eval", client=client)
        result = redactor.redact(text)
        self.assertEqual(len(result.categories), 5)
        self.assertIn(
            "amount: SAR 240.00\ndate: 2026-01-31\ntenant_ref: 0123456789abcdef",
            result.text,
        )
        self.assertNotIn("PORTFOLIO_", result.text)
        self.assertEqual(result.categories, tuple(sorted(result.categories)))
        self.assertEqual(
            client.events[0][1]["inspect_config"], client.events[1][1]["inspect_config"]
        )
        config = client.events[0][1]["inspect_config"]
        names = {v["name"] for v in config["info_types"]} | {
            v["info_type"]["name"] for v in config["custom_info_types"]
        }
        transformed = client.events[1][1]["deidentify_config"][
            "info_type_transformations"
        ]["transformations"]
        self.assertEqual({v["info_types"][0]["name"] for v in transformed}, names)
        self.assertTrue(all(e[2] is None for e in client.events))
        self.assertEqual(
            redactor.operation_counts,
            {"inspect_attempted": 0, "deidentify_attempted": 0},
        )

    def test_no_prefix_age_validity_inference_and_no_amount_exemption(self):
        for prefix in ("111", "112", "21"):
            text = "ID number: " + prefix + "0" * 20
            result = GoogleSDPContextRedactor(
                "synthetic-eval", client=self.client(text)
            ).redact(text)
            self.assertEqual(result.text, "ID number: SAUDI_NATIONAL_ID")
        text = "amount: fixture@example.invalid"
        self.assertEqual(
            GoogleSDPContextRedactor("synthetic-eval", client=self.client(text))
            .redact(text)
            .text,
            "amount: EMAIL_ADDRESS",
        )

    def test_spelling_exact_boundaries_and_no_fuzzy_matching(self):
        self.assertTrue(reference_spans("العوية: 0000000000"))
        for text in (
            "العويه: 0000000000",
            "ID: 0000",
            "account: 0000",
            '"National ID": 0000',
            "not a National ID: 0000",
            "National ID: 00",
            "National ID: " + "0" * 33,
        ):
            self.assertEqual(reference_spans(text), [])
        self.assertTrue(reference_spans("National ID: 0000; not a real identity"))

    def test_unknown_truncated_overlap_and_byte_offset_failure_blocks_second_rpc(self):
        text = "هوية: ٠٠٠٠٠٠٠٠٠٠"
        for change in ("unknown", "truncated", "overlap", "bytes"):
            client = self.client(text)
            response = client.inspect_result
            if change == "unknown":
                response.result.findings[0].info_type.name = "UNAPPROVED"
            if change == "truncated":
                response.result.findings_truncated = True
            if change == "overlap":
                response.result.findings *= 2
            if change == "bytes":
                response.result.findings[0].location.byte_range.start = 0
            with self.assertRaises(base.GoogleSDPFailure):
                GoogleSDPContextRedactor("synthetic-eval", client=client).redact(text)
            self.assertEqual(len(client.events), 1)

    def test_partial_transformation_and_leakage_remain_fail_closed(self):
        text = "National ID: 0000000000"
        client = self.client(text)
        client.deidentify_result.item.value = text
        with self.assertRaises(base.GoogleSDPFailure) as caught:
            GoogleSDPContextRedactor("synthetic-eval", client=client).redact(text)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(str(caught.exception), "redaction:provider_failure")

    def test_budget_shared_across_context_and_seed_and_no_request_configuration(self):
        text = "National ID: 0000000000"
        budget = base.ContentAttemptBudget(2)
        first = GoogleSDPContextRedactor(
            "synthetic-eval", client=self.client(text), budget=budget
        )
        first.redact(text)
        client = FakeClient()
        second = base.GoogleSDPRedactor("synthetic-eval", client=client, budget=budget)
        with self.assertRaises(base.GoogleSDPFailure):
            second.redact("Contact fixture@example.invalid")
        self.assertEqual(client.events, [])
        for kwargs in (
            {"region": "global"},
            {"endpoint": "attacker.invalid"},
            {"policy": {}},
            {"credentials": "untrusted"},
        ):
            with self.assertRaises(TypeError):
                GoogleSDPContextRedactor("synthetic-eval", **kwargs)

    def test_seed_defaults_and_authority_factories_unchanged(self):
        self.assertEqual(
            set(
                base.GoogleSDPRedactor(
                    "synthetic-eval", client=FakeClient()
                )._type_map()
            ),
            {"EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD_NUMBER"},
        )
        for path in ("runtime/agents/demo.py", "scripts/serve-demo-agents.py"):
            self.assertNotIn(
                "GoogleSDPContextRedactor",
                (Path(__file__).resolve().parents[3] / path).read_text(),
            )


try:
    from google.cloud import dlp_v2
except ImportError:
    dlp_v2 = None


@unittest.skipIf(dlp_v2 is None, "mandatory separate locked SDK gate")
class ContextSDKTests(unittest.TestCase):
    def test_real_sdk_capture_groups_hotword_shape_and_matching_requests(self):
        config = load_policy()["inspect_config"]
        inspect = dlp_v2.InspectContentRequest(
            parent="projects/synthetic-eval/locations/us-east1",
            item={"value": "synthetic"},
            inspect_config=config,
        )
        deidentify = dlp_v2.DeidentifyContentRequest(
            parent=inspect.parent,
            item=inspect.item,
            inspect_config=config,
            deidentify_config={
                "info_type_transformations": {
                    "transformations": [
                        {
                            "info_types": [{"name": n}],
                            "primitive_transformation": {
                                "replace_with_info_type_config": {}
                            },
                        }
                        for n in load_policy()["mapping"]
                    ]
                }
            },
        )
        self.assertEqual(inspect.inspect_config, deidentify.inspect_config)
        self.assertTrue(
            all(
                list(v.regex.group_indexes) == [1]
                for v in inspect.inspect_config.custom_info_types
            )
        )
        # Proximity rules can express likelihood adjustments, not exact adjacency,
        # negation or value attachment. They are deliberately not selected.
        rule = dlp_v2.CustomInfoType.DetectionRule.HotwordRule(
            hotword_regex={"pattern": "National ID"},
            proximity={"window_before": 32},
            likelihood_adjustment={"fixed_likelihood": "VERY_LIKELY"},
        )
        self.assertEqual(rule.proximity.window_before, 32)
