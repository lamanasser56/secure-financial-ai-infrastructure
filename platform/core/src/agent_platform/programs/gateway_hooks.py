"""Image-owned LiteLLM proxy hook: keep Gemini thought signatures inside
the gateway.

Gemini 3.x attaches an opaque thoughtSignature to its replies and LiteLLM 1.104.0 surfaces it as
message.provider_specific_fields.thought_signatures. The provider validates signatures only on native function-call
parts within the current turn. This platform never uses native function calling (the core admission rejects
tool_calls) and every model request is stateless (one system and one user message; no model turn is replayed), so
there is no signature round-trip to preserve. The signature is removed here, before the response leaves the gateway:
the app and its output validator never receive it, and it is never logged. After a successful call the hook also
writes one bounded audit line (`gateway_request`: request ID, key alias, resolved model, token total, cost; never a
prompt, a reply or a key value) so the gateway's trace line carries the caller's request ID. Any other provider-specific field is left
in place, so the core admission still rejects it (fail closed).

Thought text: the profile requests thinkingLevel=low, which LiteLLM 1.104.0 can only send with includeThoughts=true
(owner decision 2026-10-11: thinkingLevel=minimal failed the decision schema; the qualified core fixes max_tokens at
1024, which the default level can exhaust). LiteLLM puts that text in message.reasoning_content and
message.thinking_blocks. Both are removed here, whatever their value, so thought text stays inside the gateway: it is
never sent to the app and never logged (turn_off_message_logging; no logging callback is configured). The answer
itself is message.content, which LiteLLM builds from the non-thought parts only. LiteLLM also sets message.images as
an empty list on every Gemini reply; only that empty placeholder is removed, so a real image still reaches the core
admission and is rejected (fail closed).
"""
import json
import re
import time

try:
    from litellm.integrations.custom_logger import CustomLogger
except ImportError:  # offline tests exercise the pure helpers below without LiteLLM installed
    CustomLogger = object

REQUEST_ID = re.compile(r'[0-9a-f]{32}')
KEY_ALIAS = re.compile(r'[a-z][a-z0-9-]{1,40}')
MODEL_NAME = re.compile(r'[A-Za-z0-9._/:-]{1,80}')


def audit_fields(data, user_api_key_dict, response):
    """One bounded audit record for a completed gateway request: the caller's request ID (header or request metadata,
    exact 32-hex shape only), the key alias, the resolved model name, total tokens and LiteLLM's response cost.
    Never the prompt, the reply or any key value. Returns None when there is nothing safe to say."""
    try:
        metadata = data.get('metadata') if isinstance(data, dict) else None
        headers = ((data or {}).get('proxy_server_request') or {}).get('headers') or {}
        candidates = [(metadata or {}).get('request_id'), headers.get('x-request-id'), headers.get('X-Request-ID')]
        request_id = next((c for c in candidates if isinstance(c, str) and REQUEST_ID.fullmatch(c)), None)
        alias = getattr(user_api_key_dict, 'key_alias', None)
        model = getattr(response, 'model', None)
        tokens = getattr(getattr(response, 'usage', None), 'total_tokens', None)
        cost = (getattr(response, '_hidden_params', None) or {}).get('response_cost')
        return {'request_id': request_id,
                'key_alias': alias if isinstance(alias, str) and KEY_ALIAS.fullmatch(alias) and not alias.startswith('sk-') else None,
                'model': model if isinstance(model, str) and MODEL_NAME.fullmatch(model) else None,
                'total_tokens': tokens if type(tokens) is int and tokens >= 0 else None,
                'cost_usd': round(float(cost), 6) if isinstance(cost, (int, float)) and 0 <= cost < 1000 else None}
    except Exception:
        return None


def emit_audit(fields):
    """Same one-line JSON shape as agent_platform.audit.emit (this module belongs to the gateway image)."""
    print(json.dumps({'audit_event': 'gateway_request', 'component': 'gateway', 'at': round(time.time(), 3), **fields},
                     sort_keys=True, separators=(',', ':')), flush=True)


def strip_thought_signatures(response):
    """Remove provider_specific_fields.thought_signatures and thought text from each choice; return how many signatures
    were removed."""
    removed = 0
    for choice in getattr(response, 'choices', None) or []:
        message = getattr(choice, 'message', None)
        fields = getattr(message, 'provider_specific_fields', None)
        if isinstance(fields, dict) and 'thought_signatures' in fields:
            removed += 1
            rest = {key: value for key, value in fields.items() if key != 'thought_signatures'}
            message.provider_specific_fields = rest or None
        for name in ('reasoning_content', 'thinking_blocks'):
            if hasattr(message, name):
                delattr(message, name)  # as LiteLLM's Message does for absent fields, so it is not serialized
        images = getattr(message, 'images', None)
        if isinstance(images, list) and not images:
            delattr(message, 'images')
    return removed


class ThoughtSignatureBoundary(CustomLogger):
    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        strip_thought_signatures(response)
        fields = audit_fields(data, user_api_key_dict, response)
        if fields is not None:  # an audit failure must never change or block the response
            try:
                emit_audit(fields)
            except Exception:
                pass
        return response


thought_signature_boundary = ThoughtSignatureBoundary()
