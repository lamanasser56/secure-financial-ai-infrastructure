# Kubernetes API audit logging runbook

The [policy](../../k3s/audit-policy.yaml) records request metadata and excludes Secret bodies and other request/response bodies. It is an offline configuration artifact. Installation requires cluster-owner access to control-plane configuration and an approved restart window; this repository does not perform it.

Before installation, identify the actual control-plane distribution, audit-flag support, durable log destination, filesystem permissions, rotation, retention, access and incident handling. After installation, generate synthetic API calls and verify metadata capture, protected-body absence, logging health and bounded disk growth. Test rollback using an independent host-management path.

If the API server fails to recover, protected content is logged, or disk growth threatens the control plane, restore the prior configuration and record the qualification as failed. Application audit events and Langfuse traces are separate systems.
