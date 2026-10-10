# Claims matrix (Phase E agent platform)

A claim is **live-tested** only after the full live chain has passed and the evidence file is committed. Until then
it is **designed** (implemented, with offline or plan-level checks only). This file feeds the README claims matrix.

| Claim | Status | Evidence |
|---|---|---|
| No internet egress: no Cloud NAT, no external IPs; Google APIs via Private Google Access, and the two `rep.googleapis.com` endpoints (Vertex AI `us`, Sensitive Data Protection `us-east1`) via Private Service Connect regional endpoints with private DNS zones | designed (live chain pending) | `platform/clouds/gke/terraform/module/private_endpoints.tf`; Terraform apply 8/8 and re-plan 0 changes (2026-10-10); redactor Pod resolved the SDP hostname to an internal 10.x address (2026-10-10). Becomes live-tested when `docs/evidence/requalification.json` passes. |
