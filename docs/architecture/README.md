# Architecture

The trusted runtime is a repository-tested control boundary, not a deployed application. [System architecture](system-architecture.md) and the [dependency map](dependency-map.md) show the trust boundaries and integration order. [Agent runtime](agent-runtime.md) defines control order; [AI gateway](ai-gateway.md) defines the only permitted provider path; [tenant architecture](tenant-architecture.md) defines identity and RLS boundaries; [network architecture](network-architecture.md) and the [TLS ingress baseline](tls-ingress-baseline.md) define network and edge requirements.

Decisions: [provider gateway](decisions/ADR-001-provider-gateway.md), [tenant authority](decisions/ADR-002-tenant-authority.md), and [image promotion](decisions/ADR-003-image-promotion.md). These are sanitized successors to the relevant infrastructure decisions in the source project. They do not import the private project's authority or deployment evidence.
