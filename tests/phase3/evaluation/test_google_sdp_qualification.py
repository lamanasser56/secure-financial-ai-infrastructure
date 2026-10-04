"""Offline fixture/scorer checks; no Google detector or API execution."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from runtime.phase3 import sdp_qualification as qualification
from runtime.phase3.trusted_runtime import SUPPORTED_ENTITIES


def replaced(case):
    provider = {
        "CREDIT_CARD": "CREDIT_CARD_NUMBER",
        "EMAIL_ADDRESS": "EMAIL_ADDRESS",
        "PHONE_NUMBER": "PHONE_NUMBER",
    }
    cursor, pieces = 0, []
    for span in case["expected_spans"]:
        pieces.extend(
            (case["text"][cursor : span["start"]], provider[span["category"]])
        )
        cursor = span["end"]
    pieces.append(case["text"][cursor:])
    return "".join(pieces)


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = qualification.load_fixtures()
        self.positive = next(
            case for case in self.fixtures["cases"] if case["kind"] == "positive"
        )

    def test_partial_provenance_matrix_never_claims_eight_class_live_corpus(self):
        self.assertEqual(len(self.fixtures["cases"]), 42)
        self.assertEqual(self.fixtures["planned_live_case_count"], 87)
        self.assertEqual(self.fixtures["unprepared_case_count"], 45)
        self.assertEqual(
            set(self.fixtures["blocked_categories"]),
            {
                "IBAN_CODE",
                "SAUDI_BANK_ACCOUNT",
                "SAUDI_NATIONAL_ID",
                "SAUDI_RESIDENT_ID",
                "SAUDI_VAT_ID",
            },
        )
        self.assertEqual(
            {case["language"] for case in self.fixtures["cases"]}, {"en", "ar", "mixed"}
        )
        for category in qualification.SAFE_CLASSES:
            for language in qualification.LANGUAGES:
                positive = [
                    case
                    for case in self.fixtures["cases"]
                    if case["kind"] == "positive"
                    and case["language"] == language
                    and case["target_categories"] == [category]
                ]
                negatives = [
                    case
                    for case in self.fixtures["cases"]
                    if case["kind"] == "negative"
                    and case["language"] == language
                    and case["target_categories"] == [category]
                ]
                self.assertEqual((len(positive), len(negatives)), (2, 1))

    def test_preparation_summary_is_blocked_and_thresholds_cannot_be_lowered(self):
        summary = qualification.preparation_summary()
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["live_accuracy"], "unmeasured")
        self.assertEqual(summary["content_sdk_attempts"], 0)
        acceptance = qualification.ROOT / "evaluation/google-sdp-agent/acceptance.json"
        original = Path.read_text
        for key, changed in (
            ("max_false_negatives_per_class_language", 1),
            ("max_false_positives_per_class_language", True),
            ("max_leaked_spans", 1),
            ("approved_for_execution", True),
        ):
            weakened = json.loads(original(acceptance))
            weakened[key] = changed
            with patch.object(
                Path,
                "read_text",
                lambda path, *args, **kwargs: (
                    json.dumps(weakened)
                    if path == acceptance
                    else original(path, *args, **kwargs)
                ),
            ):
                with self.assertRaises(qualification.QualificationFailure):
                    qualification.preparation_summary()

    def test_historical_candidate_inputs_remain_separate_without_inheriting_signature(
        self,
    ):
        record = json.loads(
            (
                qualification.ROOT / "evaluation/google-sdp-agent/qualification.json"
            ).read_text()
        )
        self.assertEqual(record["status"], "blocked_full_campaign")
        self.assertEqual(record["google_quality"], "unmeasured")
        self.assertFalse(record["published"])
        self.assertFalse(record["signed"])
        self.assertFalse(record["authority_changed"])
        for group in ("image_source_input_sha256", "qualification_source_input_sha256"):
            for path, expected in record[group].items():
                if path == "runtime/phase3/google_sdp_adapter.py":
                    self.assertEqual(
                        expected,
                        "e0bdc6bc845498842c6c7d439ebc95e9a12652583c9c54aecf5a8dba0dcdb524",
                    )
                    current = json.loads(
                        (
                            qualification.ROOT
                            / "evaluation/google-sdp-context/qualification.json"
                        ).read_text()
                    )
                    self.assertEqual(
                        hashlib.sha256(
                            (qualification.ROOT / path).read_bytes()
                        ).hexdigest(),
                        current["source_input_sha256"][path],
                    )
                    continue
                self.assertEqual(
                    hashlib.sha256(
                        (qualification.ROOT / path).read_bytes()
                    ).hexdigest(),
                    expected,
                    path,
                )
        artifact = record["candidate"]
        self.assertIsNone(artifact["registry_manifest_digest"])
        self.assertIsNone(artifact["signature"])
        self.assertEqual(artifact["archive_sha256"][0], artifact["archive_sha256"][1])
        self.assertEqual((artifact["policy_exit"], artifact["exception_count"]), (0, 0))
        self.assertEqual(
            (
                artifact["vulnerabilities"]["HIGH"],
                artifact["vulnerabilities"]["CRITICAL"],
            ),
            (0, 0),
        )
        for expected in artifact["evidence_sha256"].values():
            self.assertRegex(expected, "^[0-9a-f]{64}$")

    def test_exact_labels_and_partial_metrics_never_award_google_accuracy(self):
        # Label-replay tests scoring, NOT Google detection. Missing class rows stay uncovered.
        results = [
            qualification.score_case(case, case["expected_spans"], replaced(case))
            for case in self.fixtures["cases"]
        ]
        totals = qualification.aggregate(results)
        self.assertTrue(totals["all_cases_passed"])
        self.assertFalse(totals["required_coverage_complete"])
        self.assertEqual(
            sum(row["status"] == "uncovered" for row in totals["rows"]), 15
        )
        rendered = json.dumps(results, ensure_ascii=False)
        for case in self.fixtures["cases"]:
            for span in case["expected_spans"]:
                self.assertFalse(
                    case["text"][span["start"] : span["end"]] in rendered,
                    "raw value in sanitized scorer result",
                )
        self.assertNotIn('"start"', rendered)
        self.assertNotIn('"text"', rendered)

    def test_repeated_identifiers_and_wrong_category_cannot_pass_by_category_set(self):
        case = deepcopy(self.positive)
        fragment = case["text"][
            case["expected_spans"][0]["start"] : case["expected_spans"][0]["end"]
        ]
        offset = len(case["text"]) + 1
        case["text"] += " " + fragment
        case["expected_spans"].append(
            {
                "start": offset,
                "end": offset + len(fragment),
                "category": "EMAIL_ADDRESS",
            }
        )
        result = qualification.score_case(
            case, case["expected_spans"][:1], replaced(case)
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["counts"]["EMAIL_ADDRESS"]["fn"], 1)
        wrong = deepcopy(case["expected_spans"])
        wrong[0]["category"] = "PHONE_NUMBER"
        result = qualification.score_case(case, wrong, replaced(case))
        self.assertEqual(result["counts"]["EMAIL_ADDRESS"]["fn"], 1)
        self.assertEqual(result["counts"]["PHONE_NUMBER"]["fp"], 1)

    def test_partial_leakage_refusal_and_safe_text_changes_each_fail(self):
        case = self.positive
        for value in (case["text"], replaced(case).replace("240.00", "24000"), None):
            result = qualification.score_case(case, case["expected_spans"], value)
            self.assertFalse(result["passed"])
            row = next(
                row
                for row in qualification.aggregate([result])["rows"]
                if row["category"] == "EMAIL_ADDRESS"
                and row["language"] == case["language"]
            )
            self.assertEqual(row["status"], "fail")
        refused = qualification.score_case(case, [], None)
        self.assertEqual(refused["counts"]["EMAIL_ADDRESS"]["tp"], 0)
        self.assertEqual(refused["counts"]["EMAIL_ADDRESS"]["fn"], 1)

    def test_negative_control_preserves_business_values(self):
        case = next(
            case for case in self.fixtures["cases"] if case["kind"] == "negative"
        )
        self.assertTrue(qualification.score_case(case, [], case["text"])["passed"])
        self.assertFalse(qualification.score_case(case, [], "changed")["passed"])
        self.assertFalse(
            qualification.score_case(
                case,
                [{"start": 0, "end": 1, "category": "EMAIL_ADDRESS"}],
                case["text"],
            )["passed"]
        )
        false_detection = qualification.score_case(
            case, [{"start": 0, "end": 1, "category": "EMAIL_ADDRESS"}], case["text"]
        )
        row = next(
            row
            for row in qualification.aggregate([false_detection])["rows"]
            if row["category"] == "EMAIL_ADDRESS"
            and row["language"] == case["language"]
        )
        self.assertEqual((row["expected"], row["fp"], row["status"]), (0, 1, "fail"))

    def test_invalid_labels_provenance_and_duplicate_json_are_sanitized(self):
        for invalid in (
            [{"start": True, "end": 2, "category": "EMAIL_ADDRESS"}],
            [*self.positive["expected_spans"], *self.positive["expected_spans"]],
            [{"start": 0, "end": 99999, "category": "EMAIL_ADDRESS"}],
        ):
            with self.assertRaises(qualification.QualificationFailure) as error:
                qualification.score_case(self.positive, invalid, None)
            self.assertEqual(str(error.exception), "qualification:invalid_input")
        with self.assertRaises(ValueError):
            qualification._safe_fragment(
                "+966-real-value-not-safe", "PHONE_NUMBER", ["nanpa-reserved-555"]
            )
        with self.assertRaises(ValueError):
            qualification._closed_pairs([("a", 1), ("a", 2)])
        broken = deepcopy(self.fixtures)
        broken["cases"][0]["expected_spans"][0]["category"] = "SAUDI_NATIONAL_ID"
        with patch.object(
            Path,
            "read_text",
            side_effect=[
                json.dumps(broken),
                (
                    qualification.ROOT
                    / "evaluation/google-sdp-agent/offline-fixtures.schema.json"
                ).read_text(),
            ],
        ):
            with self.assertRaises(qualification.QualificationFailure):
                qualification.load_fixtures()

    def test_historical_seed_outcome_and_corpus_are_not_reclassified(self):
        seed = json.loads(
            (qualification.ROOT / "evaluation/google-sdp/corpus.json").read_text()
        )
        self.assertEqual(len(seed["cases"]), 9)
        self.assertEqual(
            sum(
                case["expected"]["expectation"] == "observation_only"
                for case in seed["cases"].values()
            ),
            3,
        )
        self.assertEqual(
            set(SUPPORTED_ENTITIES),
            qualification.SAFE_CLASSES | qualification.BLOCKED_CLASSES,
        )


if __name__ == "__main__":
    unittest.main()
