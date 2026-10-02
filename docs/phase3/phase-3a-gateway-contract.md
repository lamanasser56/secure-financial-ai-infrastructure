# Phase 3A gateway contract

LiteLLM is the sole provider gateway. The [ConfigMap](../../kubernetes/apps/litellm/configmap.yaml) exposes `secure-financial-chat` as the only client model alias, disables fallbacks and retries, and avoids verbose request logging. Provider model, project and region remain explicit placeholders. An externally delivered `PORTFOLIO_LITELLM_MASTER_KEY` is required for client authentication; the [example Secret](../../kubernetes/secret-templates/litellm-master-key.secret.example.yaml) is intentionally non-deployable.

The [Deployment](../../kubernetes/apps/litellm/deployment.yaml) runs non-root, drops capabilities, uses a read-only root filesystem, declares resources and has startup, liveness and readiness probes. Its public HTTPS egress allowance is not a provider-only guarantee. The target CNI, cloud identity binding, provider role, key lifecycle and synthetic live request require validation before use.

An application must not receive the administrative master key or a provider credential. A scoped internal gateway credential and authorization policy are integration-dependent. A local render is static evidence only.
