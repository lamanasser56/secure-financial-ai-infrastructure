# Phase 4B tool invocation contract

The [request schema](../../contracts/phase4/tool-invocation-request.schema.json) accepts only schema version, request ID, tool ID and arguments; it carries no tenant or authorization decision. The [response schema](../../contracts/phase4/tool-invocation-response.schema.json) is a closed success-or-failure envelope. [OpenAPI](../../contracts/phase4/openapi.yaml) describes a future internal endpoint; no server is deployed.

The [invocation validator](../../runtime/phase4/tool_invocation.py) first authenticates and resolves tenant context, looks up routing metadata, authorizes the registry-declared action, checks readiness, then validates the request and arguments. Authorization precedes disclosure of a tool's enabled or schema state. Recursive tenant-shaped-key rejection prevents arguments from overriding server-derived context. Output validation is required before constructing a success response.

An invalid request, unknown tool, missing schema, malformed output or unauthorized action fails closed with a bounded stage/category pair. The [example input and output schemas](../../contracts/phase4/tools/) are synthetic. Passing this contract does not call a tool, Presidio, LiteLLM or a provider.
