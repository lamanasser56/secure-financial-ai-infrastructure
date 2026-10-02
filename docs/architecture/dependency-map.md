# Infrastructure dependency map

| Control | Required predecessor or integration | Repository status |
| --- | --- | --- |
| Tenant context | Application-authenticated identity | Contract and synthetic tests |
| Authorization | Trusted tenant context and product permission data | Contract and synthetic tests |
| Input validation and policy | Authorized request | Reference runtime and tests |
| Presidio redaction | Validated, permitted input | Internal service templates and HTTP adapter |
| LiteLLM provider gateway | Successful redaction and external secret delivery | Internal template and HTTP adapter |
| Cloud provider access | Target identity binding, approved model and region | Integration-dependent |
| Output validation | Untrusted provider response | Reference runtime and tests |
| Tool execution | Registry, policy, approval, application-owned executor | Eligibility contract only |
| Product tenant isolation | Authoritative product schema and runtime roles | Reference SQL only |
| Monitoring and audit storage | Approved sink, retention and access owner | Schemas and design only |

The [system architecture](system-architecture.md) identifies the trust boundaries. The [operations checklist](../operations.md) lists target-cluster evidence required before production use. A component can be implemented here without its integration being complete.
