# System architecture and trust boundaries

The standalone repository owns reusable infrastructure controls and reference contracts. An integrating application owns user entry, authentication, tenant resolution, authorization data, product persistence, and tool execution. The provider and any managed data-protection service are external trust boundaries.

```text
User → application-owned entry and identity → trusted AI runtime
     → Presidio redaction → LiteLLM gateway → approved provider
     ← structured output validation ← untrusted provider response
```

The [runtime contract](../phase3/phase-3c-trusted-runtime-contract.md) fixes the control order. The [gateway contract](../phase3/phase-3a-gateway-contract.md) makes LiteLLM the sole provider path. Internal network location grants no implicit authorization. Network policy, gateway authentication, and cloud IAM are separate controls; each needs validation in the target cluster.

Reference-only [RLS SQL](../../database/README.md) demonstrates database tenant isolation without claiming ownership of product tables. The [Phase 4 contracts](../phase4/README.md) define governed tool eligibility without deploying a tool executor. The [observability baseline](../observability.md) permits bounded metadata only. These distinctions prevent a repository artifact from being presented as deployed evidence.
