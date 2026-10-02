# Phase 3C trusted runtime contract

The [coordinator](../../runtime/phase3/trusted_runtime.py) orders Authentication → Tenant Context → Authorization → Structured Input Validation → Policy → Analyzer → Anonymizer → LiteLLM → Structured Output Validation. Pre-provider rejection yields zero gateway and provider calls. The model alias is `secure-financial-chat` and request bodies cannot select a tenant or provider.

The [request](../../contracts/phase3/runtime-request.schema.json), [response](../../contracts/phase3/runtime-response.schema.json), and [sanitized trace](../../contracts/phase3/sanitized-trace-envelope.schema.json) schemas reject extra fields. Provider output remains untrusted until it satisfies the exact structured result shape. Failure categories are bounded; prompt text, credentials, tenant IDs and protected values cannot be emitted in the trace.

The [HTTP adapters](../../runtime/phase3/adapters.py) call internal Presidio and LiteLLM endpoints with timeouts and read the gateway key only at call time. They do not provide real authentication, tenant resolution or a deployed HTTP coordinator. Langfuse remains a design decision, and any future sink may receive only approved sanitized metadata.
