"""Offline qualification labels/scoring, not an SDP detector or live runner.

Raw fixtures and offsets remain local input. Public summaries contain only closed
case/category/language IDs and integer counts, never text, spans or text hashes.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from jsonschema import Draft202012Validator

from .trusted_runtime import SUPPORTED_ENTITIES


ROOT = Path(__file__).resolve().parents[2]
LANGUAGES = ("en", "ar", "mixed")
SAFE_CLASSES = frozenset({"EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD"})
BLOCKED_CLASSES = frozenset(SUPPORTED_ENTITIES) - SAFE_CLASSES
_EMAIL = re.compile(r"[a-z0-9._+-]+@example\.(?:com|org|invalid)", re.ASCII)
_PHONE = re.compile(r"\+1(?:[ -]?202)[ -]?555[ -]?01[0-9]{2}", re.ASCII)
_CARD_VALUES = frozenset({"4242424242424242", "5555555555554444"})


class QualificationFailure(RuntimeError):
    def __init__(self):
        super().__init__("qualification:invalid_input")


def _closed_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def load_fixtures() -> dict:
    """Fixed offline-only path; never a URL, request path or live authorization."""
    try:
        directory = ROOT / "evaluation/google-sdp-agent"
        value = json.loads(
            (directory / "offline-fixtures.json").read_text(),
            object_pairs_hook=_closed_pairs,
        )
        schema = json.loads((directory / "offline-fixtures.schema.json").read_text())
        Draft202012Validator(schema).validate(value)
        ids = set()
        for case in value["cases"]:
            if case["case_id"] in ids or len(case["text"].encode("utf-8")) > 4096:
                raise ValueError
            ids.add(case["case_id"])
            spans = _labels(case["expected_spans"], case["text"])
            for start, end, category in spans:
                _safe_fragment(
                    case["text"][start:end], category, case["provenance_ids"]
                )
            if (case["expected_action"] == "retain") != (not spans):
                raise ValueError
            if case["kind"] == "negative" and spans:
                raise ValueError
            if case["kind"] != "negative" and not spans:
                raise ValueError
            if {span[2] for span in spans} - set(case["target_categories"]):
                raise ValueError
        if (
            len(value["cases"]) != 42
            or set(value["blocked_categories"]) != BLOCKED_CLASSES
        ):
            raise ValueError
        for category in SAFE_CLASSES:
            for language in LANGUAGES:
                for kind, count in (("positive", 2), ("negative", 1)):
                    if (
                        sum(
                            case["kind"] == kind
                            and case["language"] == language
                            and case["target_categories"] == [category]
                            for case in value["cases"]
                        )
                        != count
                    ):
                        raise ValueError
        for kind, count in (("multiple", 6), ("representation", 9)):
            if sum(case["kind"] == kind for case in value["cases"]) != count:
                raise ValueError
        return value
    except Exception:
        pass
    raise QualificationFailure()


def _safe_fragment(value: str, category: str, provenance: list[str]) -> None:
    if (
        category == "EMAIL_ADDRESS"
        and "rfc2606" in provenance
        and "reserved-email-obfuscation" in provenance
        and value == "fixture [at] example [dot] invalid"
    ):
        return
    if (
        category == "EMAIL_ADDRESS"
        and "rfc2606" in provenance
        and _EMAIL.fullmatch(value)
    ):
        return
    if (
        category == "PHONE_NUMBER"
        and "nanpa-reserved-555" in provenance
        and _PHONE.fullmatch(value)
    ):
        return
    if (
        category == "CREDIT_CARD"
        and "stripe-test-cards" in provenance
        and value.replace(" ", "") in _CARD_VALUES
    ):
        return
    raise ValueError


def _labels(spans: Any, text: str) -> set[tuple[int, int, str]]:
    if type(spans) is not list or len(spans) > 1000:
        raise ValueError
    result = set()
    for span in spans:
        if type(span) is not dict or set(span) != {"start", "end", "category"}:
            raise ValueError
        start, end, category = span["start"], span["end"], span["category"]
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(text)
            or category not in SUPPORTED_ENTITIES
        ):
            raise ValueError
        item = (start, end, category)
        if item in result:
            raise ValueError
        result.add(item)
    ordered = sorted(result)
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError
    return result


def score_case(case: dict, observed: list[dict], redacted: str | None) -> dict:
    """Exact category/span matching; provider failure/refusal is not a TP."""
    try:
        expected = _labels(case["expected_spans"], case["text"])
        actual = _labels(observed, case["text"])
        valid = (
            type(redacted) is str
            and bool(redacted.strip())
            and len(redacted.encode()) <= 4096
        )
        matched = expected & actual if valid else set()
        false_positive = actual - expected
        missed = expected - matched
        # Even an undetected ground-truth value must not survive the output.
        normalized = _normalized(redacted) if valid else ""
        leaked = sum(
            valid and _normalized(case["text"][start:end]) in normalized
            for start, end, _ in expected
        )
        preservation = valid
        if not expected:
            preservation = valid and redacted == case["text"]
        else:
            cursor, pieces = 0, []
            provider_name = {
                "CREDIT_CARD": "CREDIT_CARD_NUMBER",
                "EMAIL_ADDRESS": "EMAIL_ADDRESS",
                "PHONE_NUMBER": "PHONE_NUMBER",
            }
            for start, end, category in sorted(expected):
                pieces.extend(
                    (case["text"][cursor:start], provider_name.get(category, category))
                )
                cursor = end
            pieces.append(case["text"][cursor:])
            preservation = valid and redacted == "".join(pieces)
        counts = {}
        for category in sorted(SUPPORTED_ENTITIES):
            counts[category] = {
                "tp": sum(item[2] == category for item in matched),
                "fp": sum(item[2] == category for item in false_positive),
                "fn": sum(item[2] == category for item in missed),
                "expected": sum(item[2] == category for item in expected),
            }
        passed = (
            valid and not false_positive and not missed and not leaked and preservation
        )
        return {
            "case_id": case["case_id"],
            "language": case["language"],
            "target_categories": case["target_categories"],
            "passed": bool(passed),
            "leaked_spans": leaked,
            "allowed_text_preserved": bool(preservation),
            "counts": counts,
        }
    except Exception:
        pass
    raise QualificationFailure()


def _normalized(value: str) -> str:
    return "".join(
        str(unicodedata.decimal(char)) if char.isdecimal() else char
        for char in unicodedata.normalize("NFKC", value).casefold()
        if unicodedata.category(char) != "Cf"
    )


def aggregate(results: list[dict]) -> dict:
    rows = []
    for category in sorted(SUPPORTED_ENTITIES):
        for language in LANGUAGES:
            counts = Counter()
            for case in results:
                if case["language"] == language:
                    counts.update(case["counts"][category])
            tp, fp, fn, expected = (
                counts[key] for key in ("tp", "fp", "fn", "expected")
            )
            failures = sum(
                not case["passed"] and category in case["target_categories"]
                for case in results
                if case["language"] == language
            )
            rows.append(
                {
                    "category": category,
                    "language": language,
                    "tp": tp,
                    "fp": fp,
                    "fn": fn,
                    "expected": expected,
                    "precision": tp / (tp + fp) if tp + fp else None,
                    "recall": tp / (tp + fn) if tp + fn else None,
                    "failed_cases": failures,
                    "status": (
                        "fail"
                        if fp or fn or failures
                        else "uncovered" if expected == 0 else "pass"
                    ),
                }
            )
    return {
        "rows": rows,
        "required_coverage_complete": all(row["expected"] > 0 for row in rows),
        "all_cases_passed": all(case["passed"] for case in results),
    }


def preparation_summary() -> dict:
    """Inventory and frozen gates; never substitute label replay for accuracy."""
    try:
        fixtures = load_fixtures()
        thresholds = json.loads(
            (ROOT / "evaluation/google-sdp-agent/acceptance.json").read_text(),
            object_pairs_hook=_closed_pairs,
        )
        expected = {
            "schema_version": 1,
            "scope": "proposed_eight_class_synthetic_text_campaign",
            "planned_cases": 87,
            "required_languages": list(LANGUAGES),
            "required_categories": [
                "EMAIL_ADDRESS",
                "PHONE_NUMBER",
                "CREDIT_CARD",
                "IBAN_CODE",
                "SAUDI_NATIONAL_ID",
                "SAUDI_RESIDENT_ID",
                "SAUDI_VAT_ID",
                "SAUDI_BANK_ACCOUNT",
            ],
            "max_false_negatives_per_class_language": 0,
            "max_false_positives_per_class_language": 0,
            "max_leaked_spans": 0,
            "mandatory_negatives_preserved": True,
            "mandatory_positives_must_redact": True,
            "rejected_input_is_true_positive": False,
            "missing_coverage_is_pass": False,
            "live_accuracy": "unmeasured",
            "approved_for_execution": False,
        }
        # Compare serialized values too: bool cannot masquerade as integer zero.
        if json.dumps(thresholds, sort_keys=True) != json.dumps(
            expected, sort_keys=True
        ):
            raise ValueError
        return {
            "status": "blocked",
            "scope": fixtures["scope"],
            "prepared_cases": len(fixtures["cases"]),
            "unprepared_cases": 45,
            "planned_cases": 87,
            "blocked_categories": sorted(BLOCKED_CLASSES),
            "fixture_languages": list(LANGUAGES),
            "live_accuracy": "unmeasured",
            "content_sdk_attempts": 0,
            "metadata_sdk_attempts": 0,
            "thresholds": thresholds,
        }
    except Exception:
        pass
    raise QualificationFailure()
