# platform/clouds/gke

Everything Google-specific lives here. The cloud-agnostic platform is in `platform/core`.

| Path | Purpose |
|---|---|
| `terraform/module` | reusable module: network (no NAT, Private Google Access), private cluster, pool 0⇄1, workload identities, CI WIF pool, KMS attestor + Binary Authorization, audit sink |
| `terraform/root` | this project's instance (backend prefix `portfolio/agent-platform`; bucket given at init) |
| `kubernetes` | overlay: workload-identity annotations, Retain storage class, FQDN egress, API-server egress, NetworkLogging |
| `images.json` | signed digests (reused C-qualified gateway/database/redactor; app/ops from CI) |
| `render.py` | overlay → one manifest; refuses unless every platform invariant holds |
| `lifecycle.py` | `make plan/apply/up/down/fault/attest/port-forward/inventory` |
| `attack_suite.py` | live attacks → `docs/evidence/attack-suite.json` |
| `token_guard.py` | refusing user-ADC credential guard for Terraform (no static token) |

**Contract.**
- **Inputs:** `project_id`, `project_number`, `gke_version`; image digests.
- **Outputs used by the overlay:** `control_plane_cidr`, `gateway_service_account`, the redactor account, `attestor`,
  `ci_workload_identity_provider`, `ci_service_account`.
- An `eks/` or `aks/` module provides the same outputs; see `docs/porting-guide.md`.
