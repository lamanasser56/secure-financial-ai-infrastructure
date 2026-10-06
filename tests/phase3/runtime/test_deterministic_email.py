"""Offline tests for the provider-neutral deterministic email layer (R4 design).

Everything here is deterministic local behavior. Provider results appear only as
labelled simulations; nothing here is Google or Presidio detection evidence, and
Google's recorded context-060 failures are untouched.
"""
import hashlib
import json
from pathlib import Path
import re
import unittest

from runtime.phase3.deterministic_email import DeterministicEmailRedactor, PATTERN, TOKEN, email_spans, mask
from runtime.phase3.sdp_context_policy import DIRECTORY, load_policy, reference_spans
from runtime.phase3.trusted_runtime import ControlFailure, RedactionResult, redact_checked

ROOT = Path(__file__).resolve().parents[3]
CORPUS = json.loads((DIRECTORY / "corpus.json").read_text())["cases"]


class Identity:
    """Delegate that returns its input unchanged (no other entities)."""
    def __init__(self):
        self.seen = []
    def redact(self, text):
        self.seen.append(text)
        return RedactionResult(text, ())


def values(text):
    return [text[s:e] for s, e, _ in email_spans(text)]


class Detection(unittest.TestCase):
    def test_normal_and_reserved_domain_addresses_exact_spans(self):
        for address in ["fixture@example.invalid", "fixture@example.com", "first.last+tag@sub.example.co.uk",
                        "o'neil@example.org", "x@example.test", "user@foo.example", "a@b.localhost",
                        "UPPER@EXAMPLE.COM", "n1-2_3@d-1.example.net", "user@example.xn--p1ai"]:
            for text, offset in ((address, 0), ("Email: " + address, 7), ("(" + address + ")", 1),
                                 ('"' + address + '"', 1), (address + ".", 0), ("mailto:" + address, 7)):
                with self.subTest(text=text):
                    self.assertEqual(email_spans(text), [(offset, offset + len(address), TOKEN)])

    def test_frozen_corpus_plain_email_cases_and_zero_spans_elsewhere(self):
        for case in CORPUS:
            expected = [(s["start"], s["end"], "EMAIL_ADDRESS") for s in case["expected_spans"] if s["info_type"] == "EMAIL_ADDRESS"]
            with self.subTest(case=case["case_id"]):
                self.assertEqual(email_spans(case["text"]), expected)
        self.assertEqual(sum(bool(email_spans(c["text"])) for c in CORPUS), 3)  # context-060/061/062 only

    def test_malformed_and_non_address_inputs_are_not_detected(self):
        for text in ["fixture@", "@example.invalid", "fixture@@example.invalid", "fixture@example",
                     "fixture@.invalid", "fixture@example..invalid", "fixture.@example.invalid", ".fixture@example.invalid",
                     "fixture..x@example.invalid", "fixture@-example.invalid", "fixture@example-.invalid",
                     "fixture@example.invalid-x", "fixture@example.c", "a@b.c1", "1@2.3", "fixture example.invalid",
                     "fixture [at] example [dot] invalid", "user@localhost", "x@example.com@y", "x@example.com_y",
                     "amount: SAR 240.00", "IBAN: SA0000000000000000000000", "2026-01-31", "@", "a@b",
                     "a" * 65 + "@example.com", "a@" + ".".join(["b" * 63] * 4) + ".com"]:
            with self.subTest(text=text[:40]):
                self.assertEqual(email_spans(text), [])

    def test_unicode_contexts_use_codepoint_offsets(self):
        for prefix in ["المبلغ: ", "amount المبلغ: ", "🧪 رسالة ", "البريد：", "‏المبلغ:‏ ", "é: ", "رسالة"]:
            text = prefix + "fixture@example.invalid" + "، شكرا 🧪"
            with self.subTest(prefix=prefix):
                self.assertEqual(email_spans(text), [(len(prefix), len(prefix) + 23, TOKEN)])

    def test_out_of_scope_unicode_forms_left_to_the_delegate(self):
        # Internationalized or full-width forms are not matched in part or whole.
        for text in ["فاطمة@example.com", "fixture＠example.invalid", "fixture@exämple.com", "ｆｉｘｔｕｒｅ@example.com"]:
            with self.subTest(text=text):
                self.assertEqual(email_spans(text), [])

    def test_multiple_adjacent_addresses_sorted_non_overlapping(self):
        text = "a@example.com,b@example.org;c@example.invalid، d@example.test e@example.com"
        spans = email_spans(text)
        self.assertEqual(values(text), ["a@example.com", "b@example.org", "c@example.invalid", "d@example.test", "e@example.com"])
        self.assertTrue(all(l[1] <= r[0] for l, r in zip(spans, spans[1:])))

    def test_pattern_has_one_group_and_input_bound(self):
        self.assertEqual(PATTERN.groups, 1)
        with self.assertRaises(ControlFailure):
            email_spans("x" * 16385)
        with self.assertRaises(ControlFailure):
            email_spans(b"bytes")


class Redaction(unittest.TestCase):
    def test_numeric_and_unicode_text_preserved_outside_spans(self):
        text = "amount: SAR 240.00; fixture@example.invalid; المبلغ: SAR 200.00؛ 2026-01-31 🧪 é"
        delegate = Identity()
        result = DeterministicEmailRedactor(delegate).redact(text)
        self.assertEqual(result.text, "amount: SAR 240.00; EMAIL_ADDRESS; المبلغ: SAR 200.00؛ 2026-01-31 🧪 é")
        self.assertEqual(result.categories, ("EMAIL_ADDRESS",))
        self.assertEqual(re.findall(r"[0-9][0-9.]*", text), re.findall(r"[0-9][0-9.]*", result.text))
        self.assertNotIn("@", delegate.seen[0])  # the address never reaches the delegate

    def test_numeric_only_text_passes_through_unchanged(self):
        text = "amount: SAR 240.00; المبلغ: SAR 200.00؛ Transport: SAR 40.00; 2026-01-31"
        delegate = Identity()
        self.assertEqual(DeterministicEmailRedactor(delegate).redact(text), RedactionResult(text, ()))
        self.assertEqual(delegate.seen, [text])

    def test_inspect_and_redact_are_one_span_list(self):
        samples = [c["text"] for c in CORPUS] + ["Email: a@example.com and b@example.invalid.", "x@y.test", "no address here"]
        for text in samples:
            spans = email_spans(text)
            result = DeterministicEmailRedactor(Identity()).redact(text)
            with self.subTest(text=text[:30]):
                self.assertEqual(result.text, mask(text, spans))
                self.assertEqual("EMAIL_ADDRESS" in result.categories, bool(spans))
                self.assertEqual(email_spans(result.text), [])  # idempotent: the token is never re-detected

    def test_delegate_categories_union_and_closed_contract(self):
        class Other:
            def redact(self, text):
                return RedactionResult(text.replace("0000000000", "SAUDI_NATIONAL_ID"), ("SAUDI_NATIONAL_ID",))
        result = redact_checked(DeterministicEmailRedactor(Other()), "National ID: 0000000000; fixture@example.com")
        self.assertEqual(result, RedactionResult("National ID: SAUDI_NATIONAL_ID; EMAIL_ADDRESS", ("EMAIL_ADDRESS", "SAUDI_NATIONAL_ID")))

    def test_delegate_leak_or_malformed_result_fails_closed(self):
        class Leak:
            def redact(self, text):
                return RedactionResult("fixture@example.com " + text, ())
        class Bad:
            def redact(self, text):
                return {"text": text}
        class Unknown:
            def redact(self, text):
                return RedactionResult(text, ("NOT_A_CATEGORY",))
        for delegate, category in ((Leak(), "incomplete_redaction"), (Bad(), "malformed_result"), (Unknown(), "malformed_result")):
            with self.assertRaises(ControlFailure) as caught:
                DeterministicEmailRedactor(delegate).redact("Email: fixture@example.com")
            self.assertEqual(caught.exception.category, category)

    def test_no_overlap_with_provider_obfuscated_or_context_detectors(self):
        # Simulated provider: the frozen local reference stands in for the provider's custom detectors.
        class SimulatedProvider:
            def redact(self, text):
                spans = reference_spans(text)
                self.spans = spans
                names = load_policy()["mapping"]
                return RedactionResult(mask(text, [(s, e, names[n]) for s, e, n in spans]),
                                       tuple(sorted({names[n] for _, _, n in spans})))
        provider = SimulatedProvider()
        text = "Email: fixture@example.invalid; Contact fixture [at] example [dot] invalid\nNational ID: 0000000000"
        result = DeterministicEmailRedactor(provider).redact(text)
        self.assertEqual([n for _, _, n in provider.spans], ["PORTFOLIO_OBFUSCATED_EMAIL", "PORTFOLIO_NATIONAL_ID"])
        self.assertEqual(result.text, "Email: EMAIL_ADDRESS; Contact EMAIL_ADDRESS\nNational ID: SAUDI_NATIONAL_ID")


class CompositeScoringAmendment(unittest.TestCase):
    """Category scoring proposed by the amendment; provider part SIMULATED by the local reference."""

    def test_all_frozen_cases_pass_by_category_with_simulated_provider(self):
        mapping = load_policy()["mapping"]
        failures = []
        for case in CORPUS:
            expected = sorted((s["start"], s["end"], s["category"]) for s in case["expected_spans"])
            deterministic = [(s, e, "EMAIL_ADDRESS") for s, e, _ in email_spans(case["text"])]
            simulated = [(s, e, mapping[n]) for s, e, n in reference_spans(case["text"]) if n != "EMAIL_ADDRESS"]
            self.assertFalse(deterministic and simulated, case["case_id"])  # no frozen case mixes both
            if sorted(deterministic + simulated) != expected:
                failures.append(case["case_id"])
        self.assertEqual(failures, [])

    def test_google_records_and_subjects_unchanged(self):
        pins = {"evaluation/google-sdp-context/policy.json": "c1b782c6fd051243dec4173f903cb33607893010c7d38a6b35bc1372ddb2d4db",
                "evaluation/google-sdp-context/corpus.json": "0c07aa1e8b480e732cdcaa6e9f406661058220ad41de607af7124198e5e71eb9",
                "scripts/diagnose-sdp-email-context.py": "e7d9aea2a2886c2cdda97fad0a47920a8742d6918b1fbdf6323d8d91e64b5d63"}
        for path, digest in pins.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest, path)

    def test_layer_wired_only_where_amendment_allows(self):
        # AM-R4: only the admitted live trial composition and the composite campaign tooling use it.
        users = sorted(p.relative_to(ROOT).as_posix() for p in list((ROOT / "runtime").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py"))
                       if "deterministic_email" in p.read_text(errors="ignore") and p.name != "deterministic_email.py")
        self.assertEqual(users, ["runtime/agents/trial_composition.py", "scripts/evaluate-composite-email-campaign.py",
                                 "scripts/validate-composite-email-campaign-result.py"])


if __name__ == "__main__":
    unittest.main()
