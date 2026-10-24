# Agent Runtime Platform documentation

The current public identity is Agent Runtime Platform (Infrastructure · Security · Operations). The implementation includes GKE deployment configuration; see the [RC1 scope and limitations](releases/rc1.md) before interpreting historical runtime claims. Start with the [repository map](REPO-MAP.md).

Current platform:

- [How to view the platform](HOW-TO-VIEW.md): the console, the Financial Agent and the Platform Guide.
- [Architecture overview](architecture.md) and [ADR-008](architecture/decisions/ADR-008-persistent-agent-platform.md): trust boundaries and the platform decision.
- [Agent onboarding contract](agent-onboarding-contract.md) and [developer guide](agent-developer-guide.md): what an agent inherits and how to onboard one.
- [Claims matrix](agent-platform/claims-matrix.md), [claims inventory](security/claims-inventory.md) and [known limitations](security/known-limitations.md): what is live-tested, by which test, and what is not covered.
- [Security](security/README.md): threat model, reviews and limitations.
- [Request trace](platform/request-trace.md): the request ID and the per-turn trace.
- [Live demo runbook](operations/demo-runbook.md) and [teardown plan](agent-platform/teardown-plan.md).
- [Console design](console/design-spec.md) and the [porting guide](porting-guide.md).
- `docs/evidence/`: what was tested live, and when.

History (earlier phases, kept as a record; not the running platform):

- [Architecture](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/architecture/README.md): the reference trust boundaries, gateway, tenant model, network and decisions.
- [Phase 3](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/phase3/README.md), [Phase 4](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/phase4/README.md) and [Phase 5](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/phase5/README.md): reference contracts and qualifications.
- [Demo agents](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/agents/README.md): the offline demo agents and their live integration gates.
- [Observability](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/observability.md), [supply chain](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/supply-chain.md), [integration checklist](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/operations.md) and [operations runbooks](https://github.com/lamanasser56/secure-financial-ai-infrastructure/tree/v1-live-evidence/docs/operations/README.md).

These documents adapt the author's AI Infrastructure work from the private MASAR team repository. Product implementation, deployment identifiers, and historical approvals are excluded.
