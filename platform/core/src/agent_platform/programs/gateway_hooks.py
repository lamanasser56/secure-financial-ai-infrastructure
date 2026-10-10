"""LiteLLM proxy hook (loaded from /config by `litellm_settings.callbacks`): keep Gemini thought signatures inside
the gateway.

Gemini 3.x attaches an opaque thoughtSignature to its replies and LiteLLM 1.104.0 surfaces it as
message.provider_specific_fields.thought_signatures. The provider validates signatures only on native function-call
parts within the current turn. This platform never uses native function calling (the core admission rejects
tool_calls) and every model request is stateless (one system and one user message; no model turn is replayed), so
there is no signature round-trip to preserve. The signature is removed here, before the response leaves the gateway:
the app and its output validator never receive it, and it is never logged. Any other provider-specific field is left
in place, so the core admission still rejects it (fail closed).
"""
from litellm.integrations.custom_logger import CustomLogger


def strip_thought_signatures(response):
    """Remove exactly provider_specific_fields.thought_signatures from each choice; return how many were removed."""
    removed = 0
    for choice in getattr(response, 'choices', None) or []:
        message = getattr(choice, 'message', None)
        fields = getattr(message, 'provider_specific_fields', None)
        if isinstance(fields, dict) and 'thought_signatures' in fields:
            removed += 1
            rest = {key: value for key, value in fields.items() if key != 'thought_signatures'}
            message.provider_specific_fields = rest or None
    return removed


class ThoughtSignatureBoundary(CustomLogger):
    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        strip_thought_signatures(response)
        return response


thought_signature_boundary = ThoughtSignatureBoundary()
