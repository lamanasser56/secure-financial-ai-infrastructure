"""Closed v2 terminal records; locally durable, no transcript or credentials."""

import json
import re

from runtime.agents.audit_preparation import DurableToolAudit
from runtime.phase3.trusted_runtime import ControlFailure


class TerminalAudit(DurableToolAudit):
    """Reuse private-file/journal/commit checks with a distinct closed event.

    V1 tool governance records keep their original meaning (admission, not tool
    execution). V2 turn terminal records establish delivery admission only.
    No automatic replay or cross-database atomic execution claim.
    """

    @staticmethod
    def _encode(event):
        keys = {"schema_version", "event_id", "event_type", "occurred_at", "agent",
                "tenant_ref", "outcome", "model_attempts", "tool_attempts",
                "redaction_provider", "model_provider"}
        if (type(event) is not dict or set(event) != keys
                or event["schema_version"] != 2 or event["event_type"] != "turn_terminal"
                or event["agent"] not in {"infrastructure", "financial"}
                or event["redaction_provider"] != "simulated" or event["model_provider"] != "stub"
                or event["outcome"] not in {"completed", "blocked", "refused", "clarification_required"}
                or not re.fullmatch(r"[a-zA-Z0-9._:-]{8,128}", event["event_id"])
                or (event["tenant_ref"] is not None and not re.fullmatch(r"[a-f0-9]{16}", event["tenant_ref"]))
                or any(type(event[k]) is not int or not 0 <= event[k] <= 4
                       for k in ("model_attempts", "tool_attempts"))):
            raise ControlFailure("audit", "invalid_event")
        from datetime import datetime
        try:
            stamp = datetime.fromisoformat(event["occurred_at"])
            if stamp.tzinfo is None:
                raise ValueError
        except Exception:
            raise ControlFailure("audit", "invalid_event") from None
        return json.dumps(event, sort_keys=True, separators=(",", ":"))
