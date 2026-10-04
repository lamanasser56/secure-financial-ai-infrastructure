#!/usr/bin/env python3
"""Validate a synthetic corpus offline; live execution requires two controls.

The default command constructs no provider client and emits only a sanitized,
schema-validated result. A live run is deliberately separate from CI.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.parse import quote

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.phase3.google_sdp_adapter import (
    ENDPOINT,
    REGION,
    RPC_TIMEOUT_SECONDS,
    OVERALL_TIMEOUT_SECONDS,
    GoogleSDPRedactor,
)  # noqa: E402
from runtime.phase3.trusted_runtime import RedactionResult, RedactorClient  # noqa: E402


CORPUS_PATH = ROOT / "evaluation/google-sdp/corpus.json"
CORPUS_SCHEMA_PATH = ROOT / "evaluation/google-sdp/corpus.schema.json"
RESULT_SCHEMA_PATH = ROOT / "evaluation/google-sdp/result.schema.json"
ACK_ENV = "PORTFOLIO_GOOGLE_SDP_SYNTHETIC_ONLY_ACK"
ACK_VALUE = "I_ACKNOWLEDGE_SYNTHETIC_ONLY_GOOGLE_SDP_EVALUATION"
PROJECT_ENV = "PORTFOLIO_GOOGLE_SDP_PROJECT_ID"
ALLOWED_CATEGORIES = frozenset({"CREDIT_CARD", "EMAIL_ADDRESS", "PHONE_NUMBER"})
OUTCOME_FAIL = "FAIL AND RETAIN PRESIDIO"
OUTCOME_INCONCLUSIVE = "INCONCLUSIVE — MORE EVIDENCE REQUIRED"
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@example\.(?:com|org|invalid)")
_DOCUMENTATION_IP = re.compile(r"\b(?:192\.0\.2|198\.51\.100|203\.0\.113)\.\d{1,3}\b")


class EvaluationFailure(RuntimeError):
    """A fixed, non-sensitive failure suitable for CLI stderr."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _schema(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
        Draft202012Validator.check_schema(value)
        return value
    except Exception:
        pass
    raise EvaluationFailure("evaluation:invalid_schema")


def validate_corpus(corpus: Any) -> dict[str, Any]:
    try:
        Draft202012Validator(_schema(CORPUS_SCHEMA_PATH)).validate(corpus)
        return corpus
    except Exception:
        pass
    raise EvaluationFailure("evaluation:invalid_corpus")


def load_corpus(path: Path = CORPUS_PATH) -> dict[str, Any]:
    try:
        corpus = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except Exception:
        pass
    else:
        return validate_corpus(corpus)
    raise EvaluationFailure("evaluation:invalid_corpus")


def _live_redactor() -> RedactorClient:
    """The only real-client construction path; never reached by offline CI."""
    project_id = os.environ.get(PROJECT_ENV, "")
    try:
        return GoogleSDPRedactor(project_id, endpoint=ENDPOINT, region=REGION)
    except Exception:
        pass
    raise EvaluationFailure("evaluation:provider_failure")


def _normalized_categories(value: Any, original: str) -> list[str] | None:
    if (
        type(value) is not RedactionResult
        or type(value.text) is not str
        or not value.text.strip()
    ):
        return None
    categories = value.categories
    if type(categories) is not tuple or any(
        type(category) is not str or category not in ALLOWED_CATEGORIES
        for category in categories
    ):
        return None
    if tuple(sorted(set(categories))) != categories or (
        categories and value.text == original
    ):
        return None
    return list(categories)


def _case_result(
    case_id: str, case: dict[str, Any], redactor: RedactorClient | None
) -> dict[str, Any]:
    expected = sorted(case["expected"]["categories"])
    observed: list[str] = []
    status = "inconclusive"
    failure_code = "not_executed"
    duration_seconds = 0
    if redactor is not None:
        started = time.monotonic()
        try:
            provider_result = redactor.redact(case["input"]["text"])
        except Exception:
            provider_result = None
            failure_code = "provider_failure"
        duration_seconds = max(0, int(round(time.monotonic() - started)))
        status = "fail"
        if failure_code != "provider_failure":
            observed_value = _normalized_categories(
                provider_result, case["input"]["text"]
            )
            if observed_value is None:
                failure_code = "malformed_result"
            else:
                observed = observed_value
                expectation = case["expected"]["expectation"]
                if expectation == "observation_only":
                    status, failure_code = "inconclusive", "observation_only"
                elif expectation == "must_not_detect":
                    status, failure_code = (
                        ("fail", "unexpected_detection")
                        if observed
                        else ("pass", "none")
                    )
                elif not set(expected).issubset(observed):
                    failure_code = "missing_expected"
                elif observed != expected:
                    failure_code = "unexpected_detection"
                else:
                    status, failure_code = "pass", "none"
    return {
        "case_id": case_id,
        "expected_categories": expected,
        "observed_categories": observed,
        "status": status,
        "category_counts": {"expected": len(expected), "observed": len(observed)},
        "duration_seconds": duration_seconds,
        "failure_code": failure_code,
    }


def _validate_artifact(report: dict[str, Any], corpus: dict[str, Any]) -> None:
    try:
        Draft202012Validator(_schema(RESULT_SCHEMA_PATH)).validate(report)
        case_ids = [case["case_id"] for case in report["cases"]]
        if len(case_ids) != len(set(case_ids)) or set(case_ids) != set(corpus["cases"]):
            raise ValueError
        operations = report["provider_operations"]
        accounting = operations["accounting"]
        inspection, transformation = (
            operations["inspect_attempted"],
            operations["deidentify_attempted"],
        )
        if report["run_mode"] == "offline":
            if accounting != "not_executed" or inspection != 0 or transformation != 0:
                raise ValueError
        elif accounting == "sdk_invocation_attempts":
            if (
                type(inspection) is not int
                or type(transformation) is not int
                or not 0 <= transformation <= inspection <= len(case_ids)
            ):
                raise ValueError
        elif (
            accounting != "test_double_unavailable"
            or inspection is not None
            or transformation is not None
        ):
            raise ValueError
        rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)
        for case in corpus["cases"].values():
            value = case["input"]["text"]
            encoded = value.encode("utf-8")
            forbidden = {
                value,
                base64.b64encode(encoded).decode("ascii"),
                encoded.hex(),
                hashlib.sha256(encoded).hexdigest(),
                quote(value, safe=""),
                *_EMAIL.findall(value),
                *_DOCUMENTATION_IP.findall(value),
            }
            if any(marker and marker in rendered for marker in forbidden):
                raise ValueError
    except Exception:
        pass
    else:
        return
    raise EvaluationFailure("evaluation:invalid_artifact")


def evaluate(
    corpus: dict[str, Any] | None = None,
    *,
    live: bool = False,
    redactor: RedactorClient | None = None,
) -> dict[str, Any]:
    corpus = load_corpus() if corpus is None else validate_corpus(corpus)
    if type(live) is not bool:
        raise EvaluationFailure("evaluation:invalid_arguments")
    acknowledged = os.environ.get(ACK_ENV) == ACK_VALUE
    if live and not acknowledged:
        raise EvaluationFailure("evaluation:authorization_required")
    if live and corpus != load_corpus():
        raise EvaluationFailure("evaluation:authorization_required")
    active_redactor = (
        (redactor if redactor is not None else _live_redactor()) if live else None
    )
    initial_attempts = (
        active_redactor.operation_counts
        if type(active_redactor) is GoogleSDPRedactor and active_redactor.uses_real_sdk
        else None
    )
    cases = [
        _case_result(case_id, corpus["cases"][case_id], active_redactor)
        for case_id in sorted(corpus["cases"])
    ]
    counts = {
        status: sum(case["status"] == status for case in cases)
        for status in ("pass", "fail", "inconclusive")
    }
    aggregate_status = (
        "fail"
        if counts["fail"]
        else "inconclusive" if counts["inconclusive"] else "pass"
    )
    if initial_attempts is not None:
        final_attempts = active_redactor.operation_counts
        attempts = {
            name: final_attempts[name] - initial_attempts[name]
            for name in initial_attempts
        }
    else:
        attempts = {
            "inspect_attempted": None if live else 0,
            "deidentify_attempted": None if live else 0,
        }
    report = {
        "run_mode": "live" if live else "offline",
        "provider_operations": {
            "accounting": (
                "sdk_invocation_attempts"
                if initial_attempts is not None
                else "test_double_unavailable" if live else "not_executed"
            ),
            **attempts,
            "application_retries": 0,
            "rpc_timeout_seconds": RPC_TIMEOUT_SECONDS,
            "overall_timeout_seconds": OVERALL_TIMEOUT_SECONDS,
        },
        "cases": cases,
        "aggregate": {
            "status": aggregate_status,
            "status_counts": counts,
            "category_counts": {
                "expected": sum(case["category_counts"]["expected"] for case in cases),
                "observed": sum(case["category_counts"]["observed"] for case in cases),
            },
        },
        # An offline harness cannot satisfy the plan's security, quality,
        # operations, or image gates. It never awards the authoritative PASS.
        "outcome": OUTCOME_FAIL if counts["fail"] else OUTCOME_INCONCLUSIVE,
    }
    _validate_artifact(report, corpus)
    return report


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--live"]):
        print("evaluation:invalid_arguments", file=sys.stderr)
        return 2
    try:
        report = evaluate(live=args == ["--live"])
    except EvaluationFailure as failure:
        print(str(failure), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
