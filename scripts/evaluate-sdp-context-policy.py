#!/usr/bin/env python3
"""Fixed synthetic context-policy campaign; offline reference by default.

No raw text, values, spans, hashes of individual text or provider errors are
returned. --live plus the distinct acknowledgement are necessary but not
execution approval. Trusted deployment and frozen artifacts are mandatory.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import time

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.phase3.google_sdp_adapter import ContentAttemptBudget, GoogleSDPFailure
from runtime.phase3.sdp_context_policy import (
    DIRECTORY,
    GoogleSDPContextRedactor,
    _unique,
    load_policy,
    policy_digest,
    reference_spans,
)

ACK_ENV = "PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK"
ACK_VALUE = "I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY"
PROJECT_ENV = "PORTFOLIO_GOOGLE_SDP_PROJECT_ID"
CAMPAIGN_SECONDS = 900


def load_corpus():
    raw = (DIRECTORY / "corpus.json").read_bytes()
    if len(raw) > 131072:
        raise ValueError
    corpus = json.loads(raw, object_pairs_hook=_unique)
    schema = json.loads((DIRECTORY / "corpus.schema.json").read_text())
    Draft202012Validator(schema).validate(corpus)
    if len(corpus["cases"]) != 86:
        raise ValueError
    ids, allowed = set(), load_policy()["mapping"]
    for case in corpus["cases"]:
        if case["case_id"] in ids or len(case["text"].encode()) > 4096:
            raise ValueError
        ids.add(case["case_id"])
        cursor = 0
        for span in case["expected_spans"]:
            if (
                not cursor <= span["start"] < span["end"] <= len(case["text"])
                or allowed[span["info_type"]] != span["category"]
            ):
                raise ValueError
            cursor = span["end"]
        if (case["expected_action"] == "retain") != (not case["expected_spans"]):
            raise ValueError
    return corpus


class EvaluationRedactor(GoogleSDPContextRedactor):
    def _normalized_output(self, original, spans, validated_output):
        self._evaluation_spans = spans  # Ephemeral private scorer input only.
        return super()._normalized_output(original, spans, validated_output)


def evaluate(live=False, *, client=None, clock=time.monotonic):
    corpus = load_corpus()
    budget = ContentAttemptBudget(2 * len(corpus["cases"]))
    redactor = None
    if live:
        if client is not None or os.environ.get(ACK_ENV) != ACK_VALUE:
            raise GoogleSDPFailure()
        redactor = EvaluationRedactor(os.environ.get(PROJECT_ENV), budget=budget)
    elif client is not None:
        redactor = EvaluationRedactor("synthetic-eval", client=client, budget=budget)
    started = clock()
    result = {
        "schema_version": 1,
        "policy_id": "context-pattern-v1",
        "policy_sha256": policy_digest(),
        "mode": "live_synthetic" if live else "offline_reference",
        "google_quality": "unmeasured",
        "authority_changed": False,
        "sdk_attempts": 0,
        "injected_attempts": 0,
        "required_pass": 0,
        "required_fail": 0,
        "observations": 0,
        "unexecuted": len(corpus["cases"]),
        "cases": [],
    }
    for case in corpus["cases"]:
        if clock() - started >= CAMPAIGN_SECONDS:
            result["required_fail"] += 1
            break
        expected = {
            (s["start"], s["end"], s["info_type"]) for s in case["expected_spans"]
        }
        try:
            if redactor is None:
                actual = set(reference_spans(case["text"]))
            else:
                redactor.redact(case["text"])
                actual = {
                    (s.start, s.end, s.info_type) for s in redactor._evaluation_spans
                }
            observation = case["classification"].startswith("unsupported_")
            passed = actual == expected
            status = "OBSERVATION" if observation else "PASS" if passed else "FAIL"
            result[
                (
                    "observations"
                    if observation
                    else "required_pass" if passed else "required_fail"
                )
            ] += 1
            result["cases"].append(
                {
                    "case_id": case["case_id"],
                    "status": status,
                    "tp": len(actual & expected),
                    "fp": len(actual - expected),
                    "fn": len(expected - actual),
                }
            )
            result["unexecuted"] -= 1
            if status == "FAIL":
                break
        except Exception:
            result["required_fail"] += 1
            result["cases"].append(
                {
                    "case_id": case["case_id"],
                    "status": "FAIL_CLOSED",
                    "tp": 0,
                    "fp": 0,
                    "fn": 0,
                }
            )
            result["unexecuted"] -= 1
            break
    if redactor is not None:
        result["sdk_attempts"] = sum(redactor.operation_counts.values())
        result["injected_attempts"] = sum(redactor.injected_client_counts.values())
    result["outcome"] = (
        "FAIL_CLOSED"
        if result["required_fail"] or result["unexecuted"]
        else (
            "SYNTHETIC_POLICY_ONLY_REVIEW_REQUIRED"
            if live
            else "OFFLINE_REFERENCE_PASS_GOOGLE_UNPROVEN"
        )
    )
    if live:
        result["google_quality"] = "synthetic_policy_observations_only"
    validate_result(result)
    return result


def validate_result(result):
    Draft202012Validator(
        json.loads((DIRECTORY / "result.schema.json").read_text())
    ).validate(result)
    if len(json.dumps(result).encode()) > 16384:
        raise ValueError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        result = evaluate(args.live)
    except Exception:
        print('{"status":"blocked","reason":"redaction:provider_failure"}')
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return int(result["outcome"] == "FAIL_CLOSED")


if __name__ == "__main__":
    raise SystemExit(main())
