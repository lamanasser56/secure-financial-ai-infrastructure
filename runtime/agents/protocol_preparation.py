"""Admission for the existing JSON decision protocol; no tool execution."""

import json

from runtime.agents.schemas import validate
from runtime.phase3.trusted_runtime import ControlFailure


def _fail():
    raise ControlFailure("structured_output_validation", "output_schema_mismatch")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def completion_content(response):
    """Admit one complete assistant content response for later redaction.

    Native/legacy function calls are unsupported by this canonical JSON path.
    Reject them, mixed content, streaming chunks, refusals and truncation. Never
    dispatch tools, discover schemas or retry. The local composition uses this
    admission; its upstream remains an explicitly simulated model.
    """
    try:
        choices = response["choices"]
        if type(choices) is not list or len(choices) != 1:
            _fail()
        choice = choices[0]
        if (choice["finish_reason"] != "stop" or type(choice.get("index")) is not int
                or choice["index"] != 0):
            _fail()
        message = choice["message"]
        if (message.get("role") != "assistant"
                or set(message) - {"role", "content", "refusal", "tool_calls", "function_call", "provider_specific_fields"}
                # Locked LiteLLM/OpenAI normalization moves the optional null
                # refusal into provider metadata. Admit only these empty forms;
                # a refusal value or any additional content remains blocked.
                or message.get("provider_specific_fields") not in (None, {}, {"refusal": None})
                or any(message.get(k) is not None for k in ("refusal", "tool_calls", "function_call"))):
            _fail()
        content = message["content"]
        if type(content) is not str or not 0 < len(content.encode("utf-8")) <= 4096:
            _fail()
        return content
    except ControlFailure:
        raise
    except Exception:
        _fail()


def canonical_decision(redacted_content):
    """Validate *after* the provider-neutral redaction boundary has completed.

    Reuse the existing decision and registry input schemas. Returning a proposal
    does not authorize it; normal identity, tenant, policy and audit gates follow.
    """
    try:
        if type(redacted_content) is not str or len(redacted_content.encode()) > 4096:
            _fail()
        envelope = json.loads(redacted_content, object_pairs_hook=_unique)
        if (type(envelope) is not dict or set(envelope) != {"summary", "classification"}
                or envelope["classification"] not in {"informational", "action_required"}
                or type(envelope["summary"]) is not str):
            _fail()
        decision = validate("decision", json.loads(envelope["summary"], object_pairs_hook=_unique),
                            "structured_output_validation")
        if decision["kind"] == "tool":
            validate(decision["tool_id"] + ".input", decision["arguments"],
                     "structured_output_validation")
        return decision
    except ControlFailure:
        raise
    except Exception:
        _fail()
