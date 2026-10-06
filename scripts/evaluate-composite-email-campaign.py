#!/usr/bin/env python3
"""AM-R4 composite campaign: deterministic plain-address masking, then the unchanged
Google SDP context policy on the masked text; scored by (start, end, category).

This is never a Google qualification and never rewrites Google-only results. Offline
reference by default; --live needs both acknowledgements and is not execution
approval. In the unchanged SDP image it runs as an exact pinned -c program: the
deterministic module source is embedded by the renderer and hash-verified here.
Only minimized counts are emitted; text, spans and provider errors stay private.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import types

ROOT = Path("/app") if "__file__" not in globals() else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.phase3.google_sdp_adapter import ContentAttemptBudget, GoogleSDPFailure
from runtime.phase3.sdp_context_policy import load_policy, policy_digest, reference_spans

EMBEDDED_DETERMINISTIC_EMAIL = None  # Renderer substitutes the exact module source for -c execution.
DETERMINISTIC_EMAIL_SHA256 = "acb49418a79bb15194dcca7810d44de894934d490bd3f5f58b1e5e2f4eca14cf"
SCOPE = "composite_deterministic_email_plus_provider"
PROVIDER_SCOPE = "google_sdp_context_candidate_on_masked_text"
ACKS = {
    "PORTFOLIO_SDP_CONTEXT_SYNTHETIC_ONLY_ACK": "I_ACKNOWLEDGE_CONTEXT_PATTERN_SYNTHETIC_ONLY",
    "PORTFOLIO_COMPOSITE_EMAIL_CAMPAIGN_ACK": "I_ACKNOWLEDGE_COMPOSITE_EMAIL_CAMPAIGN_NOT_GOOGLE_QUALIFICATION",
}
PROJECT_ENV = "PORTFOLIO_GOOGLE_SDP_PROJECT_ID"
SECONDS = 900
# Provider pacing: at most one case (two SDK calls) per interval, only when a provider is
# called. 86 cases need ~172 s, well inside SECONDS. Attempts, deadline and acceptance are
# unchanged; a provider failure still stops the campaign with no retry.
CASE_INTERVAL_SECONDS = 2.0
FIELDS = {"schema_version", "scope", "provider_scope", "mode", "policy_sha256", "deterministic_email_sha256",
          "google_qualification_claimed", "authority_changed", "sdk_attempts", "injected_attempts",
          "metadata_sdk_attempts", "required_pass", "required_fail", "observations", "observation_failures",
          "operational_failures", "deterministic_email_cases", "unexecuted", "cases", "outcome"}
MODES = ("offline_reference", "offline_injected", "live_synthetic")
OUTCOMES = {"offline_reference": "OFFLINE_COMPOSITE_REFERENCE_PASS_PROVIDER_UNPROVEN",
            "offline_injected": "OFFLINE_COMPOSITE_INJECTED_PROVIDER_UNPROVEN",
            "live_synthetic": "COMPOSITE_SYNTHETIC_REVIEW_REQUIRED"}


def _source_text():
    if EMBEDDED_DETERMINISTIC_EMAIL is not None:
        return EMBEDDED_DETERMINISTIC_EMAIL
    return (ROOT / "runtime/phase3/deterministic_email.py").read_text(encoding="utf-8")


def detector():
    """Load only the exact pinned deterministic module source."""
    source = _source_text()
    if hashlib.sha256(source.encode()).hexdigest() != DETERMINISTIC_EMAIL_SHA256:
        raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
    module = types.ModuleType("runtime.phase3.deterministic_email")
    module.__package__ = "runtime.phase3"
    exec(compile(source, "deterministic_email", "exec"), module.__dict__)
    return module


def base():
    """The frozen Google-only campaign module: corpus checks and evaluation redactor."""
    spec = importlib.util.spec_from_file_location("context_campaign", ROOT / "scripts/evaluate-sdp-context-policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rendered_source(root):
    """Exact -c program text for the unchanged SDP image (used by renderer and validator)."""
    program = (Path(root) / "scripts/evaluate-composite-email-campaign.py").read_text(encoding="utf-8")
    module = (Path(root) / "runtime/phase3/deterministic_email.py").read_text(encoding="utf-8")
    marker = "EMBEDDED_DETERMINISTIC_EMAIL = None  # Renderer substitutes the exact module source for -c execution.\n"
    if program.count(marker) != 1 or hashlib.sha256(module.encode()).hexdigest() != DETERMINISTIC_EMAIL_SHA256:
        raise ValueError
    code = program.replace(marker, "EMBEDDED_DETERMINISTIC_EMAIL = " + repr(module) + "\n")
    if len(code.encode()) > 32768:
        raise ValueError
    return code


def restore(det_spans, provider, mapping, token):
    """Map provider spans from masked to original coordinates; token overlap is a mismatch."""
    tokens, shift = [], 0
    for start, end, _ in det_spans:
        masked_start = start + shift
        tokens.append((masked_start, masked_start + len(token), start, end))
        shift += len(token) - (end - start)
    restored = set()
    for start, end, name in provider:
        if any(start < m_end and m_start < end for m_start, m_end, _, _ in tokens):
            restored.add((start, end, "TOKEN_OVERLAP"))
            continue
        delta = sum((o_end - o_start) - len(token) for m_start, m_end, o_start, o_end in tokens if m_end <= start)
        restored.add((start + delta, end + delta, mapping[name]))
    return restored


def evaluate(live=False, *, client=None, clock=time.monotonic, sleep=time.sleep):
    campaign, det = base(), detector()
    cases = campaign.load_corpus()["cases"]
    if policy_digest() != campaign.POLICY_SHA256 or type(live) is not bool:
        raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
    mapping = load_policy()["mapping"]
    if CASE_INTERVAL_SECONDS * len(cases) > SECONDS / 2:
        raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
    budget = ContentAttemptBudget(2 * len(cases))
    redactor = None
    if live:
        if client is not None or any(os.environ.get(k) != v for k, v in ACKS.items()):
            raise GoogleSDPFailure("CONFIGURATION_REJECTED", "startup")
        redactor = campaign.EvaluationRedactor(os.environ.get(PROJECT_ENV), budget=budget)
    elif client is not None:
        redactor = campaign.EvaluationRedactor("synthetic-eval", client=client, budget=budget)
    mode = "live_synthetic" if live else "offline_injected" if client is not None else "offline_reference"
    result = {"schema_version": 1, "scope": SCOPE, "provider_scope": PROVIDER_SCOPE, "mode": mode,
              "policy_sha256": campaign.POLICY_SHA256, "deterministic_email_sha256": DETERMINISTIC_EMAIL_SHA256,
              "google_qualification_claimed": False, "authority_changed": False, "sdk_attempts": 0,
              "injected_attempts": 0, "metadata_sdk_attempts": 0, "required_pass": 0, "required_fail": 0,
              "observations": 0, "observation_failures": 0, "operational_failures": 0,
              "deterministic_email_cases": 0, "unexecuted": len(cases), "cases": []}
    started = clock()
    next_start = started
    for case in cases:
        observation = case["classification"].startswith("unsupported_")
        if redactor is not None:
            wait = next_start - clock()
            if wait > 0:
                sleep(min(wait, max(0.0, SECONDS - (clock() - started))))
            next_start = clock() + CASE_INTERVAL_SECONDS
        if clock() - started >= SECONDS:
            result["operational_failures"] = 1
            result["campaign_diagnostic"] = {"code": "OVERALL_TIMEOUT", "stage": "sequence"}
            break
        expected = {(s["start"], s["end"], s["category"]) for s in case["expected_spans"]}
        try:
            det_spans = det.email_spans(case["text"])
            masked = det.mask(case["text"], det_spans)
            if redactor is None:
                provider = reference_spans(masked)
            else:
                redactor.redact(masked)
                provider = [(s.start, s.end, s.info_type) for s in redactor._evaluation_spans]
            actual = {(s, e, "EMAIL_ADDRESS") for s, e, _ in det_spans} | restore(det_spans, provider, mapping, det.TOKEN)
            result["deterministic_email_cases"] += int(bool(det_spans))
            passed = actual == expected
            status = "OBSERVATION" if observation else "PASS" if passed else "FAIL"
            result["observations" if observation else "required_pass" if passed else "required_fail"] += 1
            result["cases"].append({"case_id": case["case_id"], "status": status, "tp": len(actual & expected),
                                    "fp": len(actual - expected), "fn": len(expected - actual)})
            result["unexecuted"] -= 1
            if status == "FAIL":
                break
        except Exception as error:
            if not observation:
                result["required_fail"] += 1
            result["operational_failures"] = 1
            result["observation_failures"] += int(observation)
            result["cases"].append({"case_id": case["case_id"], "status": "FAIL_CLOSED", "tp": 0, "fp": 0, "fn": 0,
                                    "diagnostic": error.diagnostic if type(error) is GoogleSDPFailure
                                    else {"code": "UNKNOWN", "stage": "sequence"}})
            result["unexecuted"] -= 1
            break
    if redactor is not None:
        result["sdk_attempts"] = sum(redactor.operation_counts.values())
        result["injected_attempts"] = sum(redactor.injected_client_counts.values())
    failed = result["required_fail"] or result["unexecuted"] or result["operational_failures"]
    result["outcome"] = "FAIL_CLOSED" if failed else OUTCOMES[mode]
    validate_result(result)
    return result


def validate_result(result):
    """Strict composite contract; independent of the Google-only validator."""
    if (type(result) is not dict or set(result) not in (FIELDS, FIELDS | {"campaign_diagnostic"})
            or len(json.dumps(result).encode()) > 16384 or result["schema_version"] != 1
            or result["scope"] != SCOPE or result["provider_scope"] != PROVIDER_SCOPE or result["mode"] not in MODES
            or result["policy_sha256"] != "c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db"
            or result["deterministic_email_sha256"] != DETERMINISTIC_EMAIL_SHA256
            or result["google_qualification_claimed"] is not False or result["authority_changed"] is not False):
        raise ValueError
    for key in ("sdk_attempts", "injected_attempts", "metadata_sdk_attempts", "required_pass", "required_fail",
                "observations", "observation_failures", "operational_failures", "deterministic_email_cases", "unexecuted"):
        if type(result[key]) is not int or result[key] < 0:
            raise ValueError
    cases, det = base().load_corpus()["cases"], detector()
    completed = result["cases"]
    mode = result["mode"]
    if ([c.get("case_id") for c in completed] != [c["case_id"] for c in cases[:len(completed)]]
            or result["unexecuted"] != len(cases) - len(completed) or result["metadata_sdk_attempts"] != 0
            or result["sdk_attempts"] + result["injected_attempts"] > 2 * len(completed)
            or (mode != "live_synthetic" and result["sdk_attempts"]) or (mode != "offline_injected" and result["injected_attempts"])):
        raise ValueError
    passes = failures = observations = observation_failures = closed = deterministic = 0
    for index, (case, row) in enumerate(zip(cases, completed)):
        status = row.get("status")
        keys = {"case_id", "status", "tp", "fp", "fn"} | ({"diagnostic"} if status == "FAIL_CLOSED" else set())
        if set(row) != keys or any(type(row[k]) is not int or not 0 <= row[k] <= 64 for k in ("tp", "fp", "fn")):
            raise ValueError
        if status in {"FAIL", "FAIL_CLOSED"} and index != len(completed) - 1:
            raise ValueError
        if status == "FAIL_CLOSED":
            if row["tp"] or row["fp"] or row["fn"]:
                raise ValueError
            closed += 1
        else:
            deterministic += int(bool(det.email_spans(case["text"])))
        if case["classification"].startswith("unsupported_"):
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
    if timeout and (closed or result["unexecuted"] == 0
                    or result["campaign_diagnostic"] != {"code": "OVERALL_TIMEOUT", "stage": "sequence"}):
        raise ValueError
    if (result["required_pass"] != passes or result["required_fail"] != failures or result["observations"] != observations
            or result["observation_failures"] != observation_failures or result["operational_failures"] != closed + int(timeout)
            or result["deterministic_email_cases"] != deterministic):
        raise ValueError
    expected = "FAIL_CLOSED" if failures or closed or timeout or result["unexecuted"] else OUTCOMES[mode]
    if result["outcome"] != expected:
        raise ValueError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        result = evaluate(args.live)
    except Exception as error:
        diagnostic = error.diagnostic if type(error) is GoogleSDPFailure else {"code": "UNKNOWN", "stage": "startup"}
        print(json.dumps({"status": "blocked", "reason": "redaction:provider_failure", "diagnostic": diagnostic}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return int(result["outcome"] == "FAIL_CLOSED")


if __name__ == "__main__":
    raise SystemExit(main())
