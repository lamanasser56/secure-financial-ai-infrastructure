# Phase 4C policy, injection, approval and audit contract

The [governance coordinator](../../runtime/phase4/tool_governance.py) applies prompt-injection assessment, policy evaluation and verified approval after authentication, tenant context, authorization and argument validation. Assessment and policy are fail-closed. Policy sees a bounded tool identity, risk, action and canonical argument digest, not raw credentials. A write or other policy-required action needs a server-side approval bound to the request, subject reference, tenant reference, tool version, action, argument digest and expiry.

The [approval](../../runtime/phase4/tool_approval.py), [policy](../../runtime/phase4/tool_policy.py), and [injection](../../runtime/phase4/prompt_injection.py) modules expose protocols and validators. The [audit module](../../runtime/phase4/tool_audit.py) constructs only the closed [AI audit-event schema](../../contracts/phase4/ai-audit-event.schema.json). It excludes raw prompts, arguments, protected values, tokens, stack traces and provider errors.

A governed invocation is not execution. The caller must supply a separate product-owned executor and durable audit sink, and must prove the same tenant and approval binding at execution time. The [governance tests](../../tests/phase4/governance/) use synthetic fixtures only.
