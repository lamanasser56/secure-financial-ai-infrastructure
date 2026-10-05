# Proposed synthetic demo identity root

This root prepares six additional resources for a separately approved fixed demo.
It preserves the existing evaluation/release identities and their state. Use only
the reviewed project and backend prefix `portfolio/agent-synthetic-demo-identity`.
No backend bootstrap, billing change, user-managed key or broad Vertex role.

The application has no cloud identity. Only the gateway KSA can impersonate the
temporary prediction GSA; only the redactor KSA can impersonate the existing SDP
runtime GSA. Namespace identity reuse within a project workload pool remains a
limitation. The permission is prediction usage, not model-specific IAM isolation.
Application/router/network gates must additionally restrict the admitted route.

Before apply, review complete native saved plans, actual API enablement and all
IAM readbacks. Any unexpected drift stops. Cleanup removes the five temporary
identity/role/binding resources; the shared Vertex API remains enabled. Do not
disable shared APIs. The [consolidated checkpoint](../../../docs/agents/integrated-synthetic-execution-checkpoint.md)
is blocked and grants no execution authority.
