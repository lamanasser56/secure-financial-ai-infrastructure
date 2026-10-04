"""Unwired, proposed live-demo input confinement; not a redaction detector.

Only fixed server-owned synthetic prompts can leave this boundary. Arbitrary
free text remains available in the existing offline UI, never promoted by this
candidate. Tenant/profile/tool authorization must still run in AgentCore.
"""

from dataclasses import dataclass


QUESTIONS = {
    "financial": frozenset({"Show my synthetic expenses", "اعرض مصاريفي التجريبية"}),
    "infrastructure": frozenset(
        {"Explain the synthetic release failure", "اشرح فشل الإصدار التجريبي"}
    ),
}
PERIODS = frozenset({"2026-01", "2026-02"})
SOURCES = frozenset({"docker-config", "archive-export", "cluster-version"})


@dataclass(frozen=True)
class CandidateSelection:
    status: str
    prompt: str | None = None


def select_candidate_input(profile, question, *, language, period=None, source=None):
    if language not in {"en", "ar"} or profile not in QUESTIONS:
        return CandidateSelection("refused")
    if type(question) is not str or question not in QUESTIONS[profile]:
        return CandidateSelection("refused")
    if profile == "financial":
        if source is not None:
            return CandidateSelection("refused")
        if period is None:
            return CandidateSelection("clarification_required")
        if period not in PERIODS:
            return CandidateSelection("unavailable_period")
        prompt = (
            f"Explain synthetic expense totals and rankings for {period}."
            if language == "en"
            else f"اشرح إجمالي المصاريف التجريبية وترتيب الفئات للفترة {period}."
        )
    else:
        if period is not None:
            return CandidateSelection("refused")
        if source is None:
            return CandidateSelection("clarification_required")
        if source not in SOURCES:
            return CandidateSelection("unavailable_source")
        prompt = (
            f"Explain the approved synthetic failure for {source}."
            if language == "en"
            else f"اشرح الفشل التجريبي المعتمد للمصدر {source}."
        )
    return CandidateSelection("selected", prompt)
