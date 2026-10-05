"""Closed v2/v3 terminal records; locally durable, no transcript or credentials."""

import json
import re

from runtime.agents.audit_preparation import DurableToolAudit
from runtime.phase3.trusted_runtime import ControlFailure
from runtime.agents.terminal_diagnostics import validate_terminal_failure


class TerminalAudit(DurableToolAudit):
    """Reuse private-file/journal/commit checks with a distinct closed event.

    V1 tool governance records keep their original meaning (admission, not tool
    execution). V2 turn terminal records establish delivery admission only. V3
    adds finite failure codes and invocation/admission/HTTP accounting. V2 history
    stays readable without inventing diagnostics or rewriting old records.
    No automatic replay or cross-database atomic execution claim.
    """

    @staticmethod
    def _encode(event):
        keys = {"schema_version", "event_id", "event_type", "occurred_at", "agent",
                "tenant_ref", "outcome", "model_attempts", "tool_attempts",
                "redaction_provider", "model_provider"}
        version = event.get('schema_version') if type(event) is dict else None
        if version == 3:
            keys |= {'terminal_failure', 'model_attempt_accounting'}
        if (type(event) is not dict or set(event) != keys
                or event["schema_version"] not in (2, 3) or event["event_type"] != "turn_terminal"
                or event["agent"] not in {"infrastructure", "financial"}
                or event["redaction_provider"] != "simulated" or event["model_provider"] != "stub"
                or event["outcome"] not in {"completed", "blocked", "refused", "clarification_required"}
                or not re.fullmatch(r"[a-zA-Z0-9._:-]{8,128}", event["event_id"])
                or (event["tenant_ref"] is not None and not re.fullmatch(r"[a-f0-9]{16}", event["tenant_ref"]))
                or any(type(event[k]) is not int or not 0 <= event[k] <= 4
                       for k in ("model_attempts", "tool_attempts"))):
            raise ControlFailure("audit", "invalid_event")
        if version == 3:
            if event['outcome'] == 'blocked':
                validate_terminal_failure(event['terminal_failure'])
            elif event['terminal_failure'] is not None:
                raise ControlFailure('audit', 'invalid_event')
            counts = event['model_attempt_accounting']
            if (type(counts) is not dict or set(counts) != {
                    'runtime_invocations', 'budget_admissions', 'budget_denials',
                    'http_attempts', 'http_responses', 'successful_traces', 'blocked_traces'}
                    or any(type(v) is not int or not 0 <= v <= 4 for v in counts.values())
                    or counts['runtime_invocations'] != event['model_attempts']
                    or counts['http_responses'] > counts['http_attempts']
                    or counts['http_attempts'] > counts['budget_admissions']
                    or counts['budget_admissions'] + counts['budget_denials'] > counts['runtime_invocations']
                    or counts['successful_traces'] + counts['blocked_traces'] > counts['runtime_invocations']):
                raise ControlFailure('audit', 'invalid_event')
        from datetime import datetime
        try:
            stamp = datetime.fromisoformat(event["occurred_at"])
            if stamp.tzinfo is None:
                raise ValueError
        except Exception:
            raise ControlFailure("audit", "invalid_event") from None
        return json.dumps(event, sort_keys=True, separators=(",", ":"))
