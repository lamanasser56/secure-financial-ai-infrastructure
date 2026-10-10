# Teardown plan (target 2026-11-06; credit expiry 2026-11-08)

The portfolio must stand without a live system. Before anything is deleted, the durable proof is committed (sanitized):
- README: architecture diagram, claims matrix, engineering story
- `docs/evidence/`: attack-suite results, image digests and signature status, requalification summary, dashboard screenshots
- the demo video script and recording

## Order (each cloud deletion is shown to the owner as one batch and then executed)
1. **Final evidence run:** `make up` → `make attack` → screenshots and recording → `make down` (last Postgres snapshot).
2. **Platform:**
   - set `deletion_protection = false` in `terraform/root`
   - `terraform destroy` (cluster, pool, network, identities, CI WIF pool, KMS key versions scheduled for destruction,
     attestor/policy reset, log bucket/sink)
   - delete the platform Postgres snapshots and the retained Postgres PV disk
3. **secure-infra-worker:** stop, then delete the VM and its disk (services 8765/8768/8769 end with it; owner approval).
4. **masar-gke** (owner-approved separately):
   - snapshot + `pg_dump` of masar-app Postgres (approved)
   - delete the cluster, then its PVC disks, including the two orphans `pvc-85fc9911` and `pvc-bb3c79bf`
5. **W18 leftovers:**
   - the approved recovery path if Cloud Shell is available; otherwise owner-approved direct deletion
   - remove network `google-sdp-evaluation`, subnet, router + NAT, NAT address, node binding; disable the node account
   - release lock generation 1791488059357282 within the approved scope
6. **Registry and state:**
   - delete images in `sdp-evaluation-images` and then the repository (digests and signatures are recorded in the repo first)
   - export the Terraform states (sanitized summaries), then delete the state bucket last
7. **Identities:** delete the remaining service accounts, custom roles (soft-deleted) and WIF pools (soft-deleted 30 days, no charge).

## Final inventory (proof that nothing billable remains)
`make inventory`, which reads: clusters, instances, disks, snapshots, addresses, forwarding rules, routers/NAT, networks,
KMS key versions (only DESTROYED/DESTROY_SCHEDULED), log buckets, Artifact Registry repositories, buckets.

- **Expected:** all empty, except the KMS key ring (no cost without enabled versions) and the free default network objects.
- **Billing check:** the Billing → Reports page shows a $0/day run rate after teardown. The owner takes a screenshot,
  because billing data has no CLI.
- The result is recorded in `docs/evidence/final-inventory.json`.
