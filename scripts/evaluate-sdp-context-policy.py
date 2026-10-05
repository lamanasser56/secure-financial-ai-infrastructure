#!/usr/bin/env python3
"""Fixed synthetic context-policy campaign; offline reference by default.

No raw text, values, spans, hashes of individual text or provider errors are
returned. --live plus the distinct acknowledgement are necessary but not
execution approval. Trusted deployment and frozen artifacts are mandatory.
"""

import argparse
import hashlib
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
DIAGNOSTIC_ACK_ENV = "PORTFOLIO_SDP_CONTEXT_DIAGNOSTIC_ONLY_ACK"
DIAGNOSTIC_ACK_VALUE = "I_ACKNOWLEDGE_CONTEXT_001_ONLY_TWO_ATTEMPTS"
DIAGNOSTIC_SECONDS = 30
CAMPAIGN_SCOPE = "context_pattern_v1_campaign"
CORPUS_SHA256 = "0c07aa1e8b480e732cdcaa6e9f406661058220ad41de607af7124198e5e71eb9"
POLICY_SHA256 = "c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db"


def load_corpus():
    raw = (DIRECTORY / "corpus.json").read_bytes()
    if (len(raw) > 131072 or hashlib.sha256(raw).hexdigest() != CORPUS_SHA256
            or policy_digest() != POLICY_SHA256):
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


def evaluate(live=False, *, client=None, clock=time.monotonic, first_case_only=False):
    corpus = load_corpus()
    if type(first_case_only) is not bool:
        raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
    cases = corpus["cases"]
    if first_case_only:
        if cases[0]["case_id"] != "context-001":
            raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
        cases = cases[:1]  # Fixed committed input; no arbitrary case/text selector.
    budget = ContentAttemptBudget(2 * len(cases))
    redactor = None
    if live:
        if client is not None or os.environ.get(ACK_ENV) != ACK_VALUE:
            raise GoogleSDPFailure()
        if first_case_only and os.environ.get(DIAGNOSTIC_ACK_ENV) != DIAGNOSTIC_ACK_VALUE:
            raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
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
        "unexecuted": len(cases),
        "cases": [],
    }
    if first_case_only:
        result["scope"] = "context_001_diagnostic_only"
    else:
        result.update(scope=CAMPAIGN_SCOPE, operational_failures=0,
                      observation_failures=0)
    for case in cases:
        observation = case["classification"].startswith("unsupported_")
        if clock() - started >= (DIAGNOSTIC_SECONDS if first_case_only else CAMPAIGN_SECONDS):
            if first_case_only:
                result["required_fail"] += 1  # Historical diagnostic contract.
            else:
                result["operational_failures"] = 1
                result["campaign_diagnostic"] = {
                    "code": "OVERALL_TIMEOUT", "stage": "sequence"
                }
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
        except Exception as error:
            if not observation:
                result["required_fail"] += 1
            if not first_case_only:
                result["operational_failures"] = 1
                result["observation_failures"] += int(observation)
            result["cases"].append(
                {
                    "case_id": case["case_id"],
                    "status": "FAIL_CLOSED",
                    "tp": 0,
                    "fp": 0,
                    "fn": 0,
                    "diagnostic": (
                        error.diagnostic if type(error) is GoogleSDPFailure
                        else {"code": "UNKNOWN", "stage": "sequence"}
                    ),
                }
            )
            result["unexecuted"] -= 1
            break
    if redactor is not None:
        result["sdk_attempts"] = sum(redactor.operation_counts.values())
        result["injected_attempts"] = sum(redactor.injected_client_counts.values())
    result["outcome"] = (
        "FAIL_CLOSED"
        if result["required_fail"] or result["unexecuted"] or result.get("operational_failures", 0)
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
    if result.get("scope") == "context_001_diagnostic_only" and (
        result["sdk_attempts"] + result["injected_attempts"] > 2
        or len(result["cases"]) > 1
        or any(c["case_id"] != "context-001" for c in result["cases"])
        or result["required_pass"] + result["required_fail"] > 1
        or result["unexecuted"] > 1
        or result["observations"] != 0
    ):
        raise ValueError
    if result.get("scope") == CAMPAIGN_SCOPE:
        cases = load_corpus()["cases"]
        completed = result["cases"]
        if ([c["case_id"] for c in completed] != [c["case_id"] for c in cases[:len(completed)]]
                or result["policy_sha256"] != POLICY_SHA256
                or result["unexecuted"] != len(cases) - len(completed)
                or result["sdk_attempts"] + result["injected_attempts"] > 2 * len(completed)
                or (result["mode"] == "offline_reference" and result["sdk_attempts"] != 0)
                or (result["mode"] == "live_synthetic" and result["injected_attempts"] != 0)):
            raise ValueError
        passes = failures = observations = observation_failures = closed = 0
        for index, (case, row) in enumerate(zip(cases, completed)):
            unsupported = case["classification"].startswith("unsupported_")
            status = row["status"]
            if status in {"FAIL", "FAIL_CLOSED"} and index != len(completed) - 1:
                raise ValueError  # No work after a failing gate.
            if status == "FAIL_CLOSED":
                if any(row[key] != 0 for key in ("tp", "fp", "fn")) or "diagnostic" not in row:
                    raise ValueError  # Placeholders are never accuracy scores.
                closed += 1
            if unsupported:
                if status not in {"OBSERVATION", "FAIL_CLOSED"}:
                    raise ValueError
                observations += int(status == "OBSERVATION")
                observation_failures += int(status == "FAIL_CLOSED")
            else:
                if status not in {"PASS", "FAIL", "FAIL_CLOSED"}:
                    raise ValueError
                passes += int(status == "PASS")
                failures += int(status in {"FAIL", "FAIL_CLOSED"})
                if status == "PASS" and (row["fp"] or row["fn"] or row["tp"] != len(case["expected_spans"])):
                    raise ValueError
                if status == "FAIL" and not (row["fp"] or row["fn"]):
                    raise ValueError
        timeout = "campaign_diagnostic" in result
        if timeout and (closed or result["unexecuted"] == 0 or result["campaign_diagnostic"] != {
                "code": "OVERALL_TIMEOUT", "stage": "sequence"}):
            raise ValueError
        if (result["required_pass"] != passes or result["required_fail"] != failures
                or result["observations"] != observations
                or result["observation_failures"] != observation_failures
                or result["operational_failures"] != closed + int(timeout)):
            raise ValueError
        expected_outcome = ("FAIL_CLOSED" if failures or closed or timeout or result["unexecuted"]
                            else "SYNTHETIC_POLICY_ONLY_REVIEW_REQUIRED" if result["mode"] == "live_synthetic"
                            else "OFFLINE_REFERENCE_PASS_GOOGLE_UNPROVEN")
        expected_quality = "synthetic_policy_observations_only" if result["mode"] == "live_synthetic" else "unmeasured"
        if result["outcome"] != expected_outcome or result["google_quality"] != expected_quality:
            raise ValueError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--diagnostic-first-case", action="store_true",
                        help="Only fixed context-001; at most two attempts, not qualification")
    args = parser.parse_args()
    try:
        result = evaluate(args.live, first_case_only=args.diagnostic_first_case)
    except Exception as error:
        diagnostic = (error.diagnostic if type(error) is GoogleSDPFailure
                      else {"code": "UNKNOWN", "stage": "startup"})
        print(json.dumps({"status": "blocked", "reason": "redaction:provider_failure",
                          "diagnostic": diagnostic}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return int(result["outcome"] == "FAIL_CLOSED")


if __name__ == "__main__":
    raise SystemExit(main())
