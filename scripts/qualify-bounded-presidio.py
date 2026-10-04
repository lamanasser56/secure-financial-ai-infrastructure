#!/usr/bin/env python3
"""Actual local Presidio HTTP qualification; sanitized metadata only.

Run inside the candidate with network disabled, repository mounted read-only.
This performs no model/provider/cloud request. It never reports corpus text.
"""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from runtime.phase3.adapters import (
    BilingualPresidioAnalyzer,
    HttpPresidioAnonymizer,
    PresidioRedactor,
)


def main():
    processes = []
    try:
        # Fixed server-selected role/port; no browser or request configuration.
        for role, port in (("analyzer", "3000"), ("anonymizer", "3001")):
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-B", "/app/server.py", role, port],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        for port in (3000, 3001):
            for _ in range(100):
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("startup_failure")
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/health", timeout=0.2
                    ) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("startup_timeout")
        redactor = PresidioRedactor(
            BilingualPresidioAnalyzer("http://127.0.0.1:3000/analyze", timeout=2),
            HttpPresidioAnonymizer("http://127.0.0.1:3001/anonymize", timeout=2),
        )
        corpus = json.loads(
            Path("tests/phase3/presidio/synthetic-cases.json").read_text()
        )
        results = []
        for case in corpus["cases"]:
            value = "".join(case["fragments"])
            if case["builder"] == "email":
                value = case["fragments"][0] + "@" + ".".join(case["fragments"][1:])
            elif case["builder"] == "saudi_iban":
                digits = value + "281000"  # SA + temporary checksum 00
                value = "SA" + str(98 - int(digits) % 97).zfill(2) + value
            for view, prefix in (
                ("en", case["context"]),
                ("ar", "بيانات اصطناعية للاختبار"),
                ("mixed", "Synthetic بيانات"),
            ):
                # The bank recognizer requires an explicit English/Arabic label.
                if case["expected_entity"] == "SAUDI_BANK_ACCOUNT":
                    prefix = "حساب مصرفي:" if view == "ar" else "bank account:"
                original = prefix + " " + value
                result = redactor.redact(original)
                passed = (
                    case["expected_entity"] in result.categories
                    and value not in result.text
                )
                results.append(
                    {
                        "case_id": case["case_id"] + "-" + view,
                        "passed": passed,
                        "categories": list(result.categories),
                    }
                )
        for number, context in (
            ("١" + "٠" * 9, "SAUDI_NATIONAL_ID"),
            ("٢" + "٠" * 9, "SAUDI_RESIDENT_ID"),
            ("٣" + "٠" * 13 + "٣", "SAUDI_VAT_ID"),
        ):
            result = redactor.redact("مرجع اصطناعي " + number)
            results.append(
                {
                    "case_id": context.lower() + "-arabic-digits",
                    "passed": context in result.categories
                    and number not in result.text,
                    "categories": list(result.categories),
                }
            )
        for identifier, original in (
            ("plain-en", "Explain synthetic Docker configuration failure."),
            ("plain-ar", "اشرح فشل إعداد Docker الاصطناعي."),
            (
                "structured-facts",
                json.dumps(
                    {
                        "period": "2026-01",
                        "source_id": "synthetic-expenses-v1",
                        "total_minor_units": 24000,
                    }
                ),
            ),
            ("ipv4", "Synthetic network 192.0.2.5"),
        ):
            result = redactor.redact(original)
            results.append(
                {
                    "case_id": identifier,
                    "passed": result.text == original and not result.categories,
                    "categories": list(result.categories),
                }
            )
        print(
            json.dumps(
                {
                    "mode": "real_presidio_local_http",
                    "external_model_requests": 0,
                    "cases": results,
                    "passed": sum(r["passed"] for r in results),
                    "total": len(results),
                },
                indent=2,
            )
        )
        return 0 if all(r["passed"] for r in results) else 1
    except Exception:
        print(
            json.dumps(
                {
                    "mode": "real_presidio_local_http",
                    "status": "blocked",
                    "reason": "required_control_failed",
                }
            )
        )
        return 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
