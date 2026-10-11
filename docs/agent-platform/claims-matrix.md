# Claims matrix (Phase E agent platform)

A claim is **live-tested** only after the full live chain has passed and the evidence file is committed. Until then
it is **designed** (implemented, with offline or plan-level checks only). This file feeds the README claims matrix.

| Claim | Status | Evidence |
|---|---|---|
| No internet egress: no Cloud NAT, no external IPs; Google APIs via Private Google Access, and the two `rep.googleapis.com` endpoints (Vertex AI `us`, Sensitive Data Protection `us-east1`) via Private Service Connect regional endpoints with private DNS zones | designed (live chain pending) | `platform/clouds/gke/terraform/module/private_endpoints.tf`; Terraform apply 8/8 and re-plan 0 changes (2026-10-10); redactor Pod resolved the SDP hostname to an internal 10.x address (2026-10-10). Becomes live-tested when `docs/evidence/requalification.json` passes. |
| The Ops Agent cannot change what a registered workload runs, even with a compromised identity: only rollout restart (template changed by the restart annotation only) and bounded scale; no rollback, no image, command, args, env, envFrom, resources, probe or label change | designed (live attack suite pending) | `platform/core/kubernetes/policies/admission.yaml`; `make test-policies` on a real kube-apiserver denies 15 template changes made as the ops-agent identity (2026-10-11). Fixes an owner-reported finding: the former rollback branch did not compare command/args/env/envFrom/resources/probes/workingDir/lifecycle/labels. |

## Recorded limitations

| Limitation | Effect | Where it is recorded |
|---|---|---|
| **Person names are not redacted.** The qualified redaction entity set (Sensitive Data Protection context + the deterministic email layer) covers card numbers, email, IBAN, phone and Saudi account/ID/VAT numbers, and has no person-name (PERSON) category. | A name typed into a question reaches the model provider as written. The covered entities are masked before the provider. The requalification redaction case (5a) therefore tests email + phone only, and no claim covers names. | `docs/agent-platform/model-requalification.md` (case 5); `runtime/phase3/trusted_runtime.py` (`SUPPORTED_ENTITIES`) |
