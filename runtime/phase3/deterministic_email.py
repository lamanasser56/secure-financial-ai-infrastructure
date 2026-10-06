"""Deterministic plain-address email masking in front of any approved redactor.

Provider-neutral. Under owner amendment AM-R4 it is wired only into the admitted live
trial composition (fixed qualification and supervised trial); local stub and the
phase3 TrustedRuntime are unchanged. One span list drives both inspection and redaction, so they cannot disagree. Masked
addresses never reach the delegate. Text outside matched spans is preserved
byte-for-byte; amounts, dates, Arabic and other Unicode text are untouched.

Scope is deliberately narrow: ASCII dot-atom local part and an ASCII multi-label
domain with an alphabetic (or punycode) top-level label, including RFC 2606/6761
reserved names such as .invalid and .test. Not detected here (left to the delegate):
quoted or IP-literal addresses, internationalized/Unicode or full-width forms, and
obfuscated "[at]/[dot]" spellings. This is not a Google or Presidio qualification.
"""
import re

from .trusted_runtime import ControlFailure, RedactionResult, SUPPORTED_ENTITIES

TOKEN = "EMAIL_ADDRESS"
_ATOM = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_TLD = r"(?:[A-Za-z]{2,63}|xn--[A-Za-z0-9-]{2,59})"
# Boundaries: no address character directly before; after, no domain/label character
# and no '@'. A sentence-final '.' is allowed and excluded from the span.
PATTERN = re.compile(
    r"(?<![A-Za-z0-9!#$%&'*+/=?^_`{|}~.@-])"
    r"(" + _ATOM + r"(?:\." + _ATOM + r")*@(?:" + _LABEL + r"\.)+" + _TLD + r")"
    r"(?![A-Za-z0-9_@-]|\.[A-Za-z0-9-])",
    re.ASCII,
)
MAX_TEXT = 16384


def email_spans(text):
    """Exact (start, end, 'EMAIL_ADDRESS') codepoint spans; sorted, non-overlapping."""
    if type(text) is not str or len(text) > MAX_TEXT:
        raise ControlFailure("presidio_analyzer", "malformed_result")
    spans = []
    for match in PATTERN.finditer(text):
        start, end = match.span(1)
        local, domain = text[start:end].rsplit("@", 1)
        if len(local) > 64 or len(domain) > 253:
            continue
        spans.append((start, end, TOKEN))
    return spans


def mask(text, spans):
    pieces, cursor = [], 0
    for start, end, token in spans:
        pieces.extend((text[cursor:start], token))
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


class DeterministicEmailRedactor:
    """Mask plain addresses, then delegate the masked text to the approved redactor.

    Only the attributes existing consumers inspect are passed through, read-only:
    the live-composition guard (analyzer/anonymizer/offline_simulation) must still
    see a simulated delegate, and budget readers see the delegate's own budget.
    """

    composite_scope = "composite_deterministic_email_plus_provider"

    def __init__(self, delegate):
        if isinstance(delegate, DeterministicEmailRedactor):
            raise ValueError("deterministic_email:nested_wrapper")
        self._delegate = delegate

    @property
    def delegate(self):
        return self._delegate

    @property
    def budget(self):
        return self._delegate.budget

    @property
    def analyzer(self):
        return getattr(self._delegate, "analyzer", None)

    @property
    def anonymizer(self):
        return getattr(self._delegate, "anonymizer", None)

    @property
    def offline_simulation(self):
        return getattr(self._delegate, "offline_simulation", False)

    def redact(self, text):
        spans = email_spans(text)
        masked = mask(text, spans)
        result = self._delegate.redact(masked)
        if type(result) is not RedactionResult or not isinstance(result.text, str):
            raise ControlFailure("presidio_anonymizer", "malformed_result")
        for start, end, _ in spans:
            if text[start:end] in result.text:
                raise ControlFailure("presidio_anonymizer", "incomplete_redaction")
        categories = set(result.categories) | ({TOKEN} if spans else set())
        if not categories <= SUPPORTED_ENTITIES:
            raise ControlFailure("presidio_anonymizer", "malformed_result")
        return RedactionResult(result.text, tuple(sorted(categories)))
