"""Portfolio Phase 4C prompt-injection assessment contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from runtime.phase3.trusted_runtime import ControlFailure


class PromptInjectionOutcome(str, Enum):
    CLEAR = "clear"
    SUSPECTED = "suspected"


SUPPORTED_INDICATOR_CATEGORIES = frozenset(
    {
        "instruction_override",
        "policy_evasion",
        "tool_manipulation",
        "data_exfiltration",
    }
)


@dataclass(frozen=True)
class PromptInjectionAssessment:
    outcome: PromptInjectionOutcome
    indicator_categories: tuple[str, ...]


class PromptInjectionAssessor(Protocol):
    def assess(self, arguments: dict[str, Any]) -> PromptInjectionAssessment: ...


def assess_prompt_injection(
    assessor: PromptInjectionAssessor,
    arguments: dict[str, Any],
) -> PromptInjectionAssessment:
    try:
        assessment = assessor.assess(dict(arguments))
    except ControlFailure as exc:
        if (
            exc.stage == "prompt_injection_assessment"
            and exc.category in {"timeout", "unavailable"}
        ):
            raise
        raise ControlFailure("prompt_injection_assessment", "unavailable") from exc
    except TimeoutError as exc:
        raise ControlFailure("prompt_injection_assessment", "timeout") from exc
    except Exception as exc:
        raise ControlFailure("prompt_injection_assessment", "unavailable") from exc

    if (
        not isinstance(assessment, PromptInjectionAssessment)
        or not isinstance(assessment.outcome, PromptInjectionOutcome)
        or not isinstance(assessment.indicator_categories, tuple)
        or any(not isinstance(item, str) for item in assessment.indicator_categories)
        or len(set(assessment.indicator_categories)) != len(assessment.indicator_categories)
    ):
        raise ControlFailure("prompt_injection_assessment", "malformed_assessment")
    if any(
        item not in SUPPORTED_INDICATOR_CATEGORIES
        for item in assessment.indicator_categories
    ):
        raise ControlFailure(
            "prompt_injection_assessment", "unsupported_indicator_category"
        )
    if (
        assessment.outcome is PromptInjectionOutcome.CLEAR
        and assessment.indicator_categories
    ):
        raise ControlFailure("prompt_injection_assessment", "malformed_assessment")
    if assessment.outcome is PromptInjectionOutcome.SUSPECTED:
        raise ControlFailure("prompt_injection_assessment", "suspected_injection")
    return assessment
