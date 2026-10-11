"""LiteLLM proxy hook (loaded from /config by `litellm_settings.callbacks`): keep Gemini thought signatures inside
the gateway.

Gemini 3.x attaches an opaque thoughtSignature to its replies and LiteLLM 1.104.0 surfaces it as
message.provider_specific_fields.thought_signatures. The provider validates signatures only on native function-call
parts within the current turn. This platform never uses native function calling (the core admission rejects
tool_calls) and every model request is stateless (one system and one user message; no model turn is replayed), so
there is no signature round-trip to preserve. The signature is removed here, before the response leaves the gateway:
the app and its output validator never receive it, and it is never logged. Any other provider-specific field is left
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
from litellm.integrations.custom_logger import CustomLogger


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
        return response


thought_signature_boundary = ThoughtSignatureBoundary()
