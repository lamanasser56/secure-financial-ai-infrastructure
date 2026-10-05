#!/usr/bin/env python3
"""Four fixed synthetic comparisons; no campaign qualification or agent wiring.

Default execution is an offline reference. Live admission requires --live and
both exact acknowledgements; this is not execution approval. The reviewed program
can run as an exact pinned -c argument in the unchanged qualified context image.
No input/case/file/endpoint/threshold selector exists. Only minimized observations
are emitted; provider responses, text, offsets and exceptions stay private.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path("/app")
sys.path.insert(0, str(ROOT))
from runtime.phase3.google_sdp_adapter import (
    ContentAttemptBudget, GoogleSDPFailure, DIAGNOSTIC_CODES, DIAGNOSTIC_STAGES,
    RPC_STATUSES, _guarded,
)
from runtime.phase3.sdp_context_policy import (
    GoogleSDPContextRedactor, load_policy, reference_spans, _unique,
)

POLICY_HASH = "c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db"
CORPUS_HASH = "0c07aa1e8b480e732cdcaa6e9f406661058220ad41de607af7124198e5e71eb9"
SCOPE = "context_060_four_comparisons_only"
IDS = ("context-060", "email-label-control", "reserved-domain-control", "numeric-retention-control")
ACKS = {
    "PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK": "I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY",
    "PORTFOLIO_SDP_EMAIL_DIAGNOSTIC_ONLY_ACK": "I_ACKNOWLEDGE_FOUR_EMAIL_COMPARISONS_EIGHT_ATTEMPTS",
}
SDK_LIMIT = 8
SECONDS = 60
LIKELIHOODS = ("LIKELIHOOD_UNSPECIFIED", "VERY_UNLIKELY", "UNLIKELY", "POSSIBLE", "LIKELY", "VERY_LIKELY")


def comparisons():
    directory = ROOT / "evaluation/google-sdp-context"
    for name, digest in (("policy.json", POLICY_HASH), ("corpus.json", CORPUS_HASH)):
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
    load_policy()
    corpus = json.loads((directory / "corpus.json").read_bytes(), object_pairs_hook=_unique)
    original = next(c for c in corpus["cases"] if c["case_id"] == "context-060")
    span, = original["expected_spans"]
    if original["classification"] != "required_policy_positive" or span["info_type"] != "EMAIL_ADDRESS" or span["category"] != "EMAIL_ADDRESS":
        raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
    value = original["text"][span["start"]:span["end"]]
    if not value.endswith("@example.invalid"):
        raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
    prefix = original["text"][:span["start"]]
    domain_control = value.removesuffix("invalid") + "com"
    numeric = "amount: SAR 240.00; المبلغ: SAR 200.00؛ Transport: SAR 40.00; 2026-01-31"
    return (
        (IDS[0], original["text"], {(span["start"], span["end"], "EMAIL_ADDRESS")}),
        (IDS[1], "Email: " + value, {(7, 7 + len(value), "EMAIL_ADDRESS")}),
        (IDS[2], prefix + domain_control, {(len(prefix), len(prefix) + len(domain_control), "EMAIL_ADDRESS")}),
        (IDS[3], numeric, set()),
    )


class DiagnosticRedactor(GoogleSDPContextRedactor):
    """Reuse all existing dispatch, byte, deadline and transformation guards."""

    def clear_observation(self):
        self._scored_spans = ()
        self._likelihoods = {}

    def _invoke(self, name, request, deadline, reservation):
        response = super()._invoke(name, request, deadline, reservation)
        if name == "inspect":
            def histogram():
                counts = Counter()
                findings = list(response.result.findings)
                if len(findings) > 1000:
                    raise ValueError
                for finding in findings:
                    code = finding.likelihood
                    if isinstance(code, bool) or not isinstance(code, int) or not 0 <= code < len(LIKELIHOODS):
                        raise ValueError
                    counts[LIKELIHOODS[code]] += 1
                return dict(counts)
            self._likelihoods = _guarded(histogram, code="MALFORMED_RESPONSE", stage="inspect_response")
        return response

    def _normalized_output(self, original, spans, validated_output):
        self._scored_spans = spans  # Private ephemeral scorer input only.
        return super()._normalized_output(original, spans, validated_output)


def evaluate(live=False, *, client=None, clock=time.monotonic):
    cases = comparisons()
    if type(live) is not bool or (live and (client is not None or any(os.environ.get(k) != v for k, v in ACKS.items()))):
        raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
    redactor = None
    if live or client is not None:
        redactor = DiagnosticRedactor(os.environ.get("PORTFOLIO_GOOGLE_SDP_PROJECT_ID") if live else "synthetic-eval", client=client, budget=ContentAttemptBudget(SDK_LIMIT))
    result = {
        "schema_version": 1, "scope": SCOPE, "policy_sha256": POLICY_HASH,
        "mode": "live_synthetic" if live else "offline_injected" if client is not None else "offline_reference",
        "google_quality": "diagnostic_observations_only" if live else "unmeasured",
        "authority_changed": False, "sdk_attempts": 0, "injected_attempts": 0,
        "metadata_sdk_attempts": 0, "operational_failures": 0, "unexecuted": 4, "observations": [],
    }
    started = clock()
    for case_id, text, expected in cases:
        if clock() - started >= SECONDS:
            result["operational_failures"] = 1
            result["sequence_diagnostic"] = {"code": "OVERALL_TIMEOUT", "stage": "sequence"}
            break
        try:
            histogram = {}
            if redactor is None:
                actual = set(reference_spans(text))
            else:
                redactor.clear_observation()
                redactor.redact(text)
                actual = {(s.start, s.end, s.info_type) for s in redactor._scored_spans}
                histogram = redactor._likelihoods
                redactor.clear_observation()
            result["observations"].append({
                "comparison_id": case_id, "status": "OBSERVATION", "min_likelihood": "POSSIBLE",
                "tp": len(actual & expected), "fp": len(actual - expected), "fn": len(expected - actual),
                "finding_count": len(actual), "returned_likelihood_counts": histogram,
                "provider_output_guards_passed": redactor is not None,
            })
        except GoogleSDPFailure as error:
            result["operational_failures"] = 1
            result["observations"].append({"comparison_id": case_id, "status": "FAIL_CLOSED", "diagnostic": error.diagnostic})
            if redactor is not None:
                redactor.clear_observation()
            break
        # A mismatch is a diagnostic observation only; never a campaign acceptance.
        # Comparing the fixed controls is explicitly part of a future approval.
    if redactor is not None:
        result["sdk_attempts"] = sum(redactor.operation_counts.values())
        result["injected_attempts"] = sum(redactor.injected_client_counts.values())
    result["unexecuted"] = 4 - len(result["observations"])
    result["outcome"] = "FAIL_CLOSED" if result["operational_failures"] else "DIAGNOSTIC_ONLY_REVIEW_REQUIRED" if live else "OFFLINE_GOOGLE_UNPROVEN"
    validate_result(result)
    return result


def validate_result(value):
    fields = {"schema_version", "scope", "policy_sha256", "mode", "google_quality", "authority_changed", "sdk_attempts", "injected_attempts", "metadata_sdk_attempts", "operational_failures", "unexecuted", "observations", "outcome"}
    if type(value) is not dict or set(value) not in (fields, fields | {"sequence_diagnostic"}) or len(json.dumps(value).encode()) > 4096:
        raise ValueError
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["scope"] != SCOPE or value["policy_sha256"] != POLICY_HASH or value["authority_changed"] is not False:
        raise ValueError
    mode = value["mode"]
    if mode not in ("offline_reference", "offline_injected", "live_synthetic"):
        raise ValueError
    if value["google_quality"] != ("diagnostic_observations_only" if mode == "live_synthetic" else "unmeasured"):
        raise ValueError
    rows = value["observations"]
    if type(rows) is not list or len(rows) > 4 or [r["comparison_id"] for r in rows] != list(IDS[:len(rows)]):
        raise ValueError
    for k, upper in (("sdk_attempts", 8), ("injected_attempts", 8), ("metadata_sdk_attempts", 0), ("operational_failures", 1), ("unexecuted", 4)):
        if type(value[k]) is not int or not 0 <= value[k] <= upper:
            raise ValueError
    if value["unexecuted"] != 4-len(rows) or value["sdk_attempts"]+value["injected_attempts"] > 2*len(rows):
        raise ValueError
    if (mode != "live_synthetic" and value["sdk_attempts"]) or (mode != "offline_injected" and value["injected_attempts"]):
        raise ValueError
    closed = 0
    for i, row in enumerate(rows):
        if row["status"] == "FAIL_CLOSED":
            if set(row) != {"comparison_id", "status", "diagnostic"} or i != len(rows)-1:
                raise ValueError
            diag = row["diagnostic"]
            if set(diag) not in ({"code", "stage"}, {"code", "stage", "rpc_status"}) or diag["code"] not in DIAGNOSTIC_CODES or diag["stage"] not in DIAGNOSTIC_STAGES or ("rpc_status" in diag and diag["rpc_status"] not in RPC_STATUSES):
                raise ValueError
            closed += 1
        else:
            if set(row) != {"comparison_id", "status", "min_likelihood", "tp", "fp", "fn", "finding_count", "returned_likelihood_counts", "provider_output_guards_passed"} or row["status"] != "OBSERVATION" or row["min_likelihood"] != "POSSIBLE":
                raise ValueError
            if any(type(row[k]) is not int or not 0 <= row[k] <= 1000 for k in ("tp", "fp", "fn", "finding_count")) or row["finding_count"] != row["tp"]+row["fp"] or row["tp"]+row["fn"] != int(i < 3):
                raise ValueError
            hist = row["returned_likelihood_counts"]
            if type(hist) is not dict or not set(hist) <= set(LIKELIHOODS) or any(type(n) is not int or not 1 <= n <= 1000 for n in hist.values()):
                raise ValueError
            if row["provider_output_guards_passed"] is not (mode != "offline_reference") or (mode != "offline_reference" and sum(hist.values()) != row["finding_count"]) or (mode == "offline_reference" and hist):
                raise ValueError
    timeout = "sequence_diagnostic" in value
    attempts = value["sdk_attempts"] + value["injected_attempts"]
    successful_attempts = 2 * (len(rows) - closed)
    if mode != "offline_reference" and not successful_attempts <= attempts <= successful_attempts + 2 * closed:
        raise ValueError
    if timeout and (closed or value["unexecuted"] == 0 or value["sequence_diagnostic"] != {"code": "OVERALL_TIMEOUT", "stage": "sequence"}):
        raise ValueError
    if value["operational_failures"] != closed+int(timeout) or (value["unexecuted"] and not value["operational_failures"]):
        raise ValueError
    expected = "FAIL_CLOSED" if value["operational_failures"] else "DIAGNOSTIC_ONLY_REVIEW_REQUIRED" if mode == "live_synthetic" else "OFFLINE_GOOGLE_UNPROVEN"
    if value["outcome"] != expected:
        raise ValueError


def read_result(raw):
    """Bounded minimized-result admission, never an arbitrary diagnostic input."""
    if type(raw) is not bytes or len(raw) > 4096:
        raise ValueError
    value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique)
    validate_result(value)
    return value


class ClosedArguments(argparse.ArgumentParser):
    def error(self, message):
        raise SystemExit("diagnostic arguments rejected") from None


if __name__ == "__main__":
    parser = ClosedArguments(description=__doc__, allow_abbrev=False)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        value = evaluate(args.live)
    except Exception as error:
        diagnostic = error.diagnostic if type(error) is GoogleSDPFailure else {"code": "UNKNOWN", "stage": "startup"}
        print(json.dumps({"status": "blocked", "reason": "redaction:provider_failure", "diagnostic": diagnostic}, sort_keys=True))
        raise SystemExit(1) from None
    print(json.dumps(value, separators=(",", ":"), sort_keys=True))
    raise SystemExit(int(bool(value["operational_failures"])))
