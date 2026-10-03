# Agent runtime boundary

An application-owned adapter authenticates a caller and resolves tenant context from trusted claims. The repository's [trusted runtime](../../runtime/phase3/trusted_runtime.py) then applies authorization, structured input validation, policy, Analyzer and Anonymizer redaction, LiteLLM, and structured output validation in that order. Untrusted requests cannot select tenant, provider, policy outcome, or redaction bypass. Failure at any required pre-provider stage stops the route before LiteLLM.

The [Phase 4 coordinator](../../runtime/phase4/tool_governance.py) qualifies tool requests against registry metadata, prompt-injection assessment, policy, and approval. It returns a governed invocation object; it never executes a tool. Product authentication, tenant resolution, tool execution, and durable audit storage are integration-dependent.

The bounded [demo agent core](../agents/architecture.md) composes that coordinator before dispatching five read-only synthetic handlers. Its offline entry points use explicitly simulated identity/model/service doubles; they do not authorize product execution or live provider access.

Only sanitized, bounded categories belong in traces and audit events. Raw prompts, documents, tool arguments, credentials, tenant IDs, and provider errors do not. See the [Phase 3 contract](../phase3/phase-3c-trusted-runtime-contract.md) and [Phase 4 contract](../phase4/phase-4c-policy-injection-approval-audit-contract.md).
