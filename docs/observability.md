# Observability baseline

The implemented runtime produces a sanitized trace envelope and the tool boundary defines a sanitized audit-event schema. These records must contain bounded control categories, a correlation reference, and an outcome. They must not contain prompts, original or redacted values, documents, tool arguments, tokens, tenant IDs, or raw exception text.

Monitoring integration is designed. An existing cluster monitoring stack should be inventoried before adding ServiceMonitors, PrometheusRules, dashboards, or alert routes. The repository does not own a monitoring Helm release and contains no scrape resource or dashboard.

Minimum target signals are control failure rates by bounded stage and category, Presidio and LiteLLM availability and latency, Kubernetes pod readiness and restarts, namespace quota pressure, NetworkPolicy enforcement, and API audit pipeline health. Labels must remain low cardinality; request, user, document, and tenant identifiers must not become metric labels.

An operational alert needs a named owner, a tested receiver, a runbook, a reviewed threshold, a missing-data behavior, and an evidence-retention decision. None of those properties is claimed by the standalone repository.
