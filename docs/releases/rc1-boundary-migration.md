# Agent Runtime Platform — trusted-boundary RC1 migration

Infrastructure · Security · Operations

This is a proposed new source/configuration release. It is not deployed, signed or live verified. Historical images, attestations, reviews, claims matrices, database disk and snapshots remain unchanged.

## Request paths

Financial example: browser → trusted Financial frontdoor (session verification) → signed per-turn capability → separate per-user untrusted Financial worker → trusted data broker (capability/audience/scope and fixed worker-key/user verification) → fixed SQL under a dedicated trusted read role and FORCE RLS. Model requests go through the trusted gateway frontend → mandatory redaction → private LiteLLM provider service → provider. No agent DB password, session signing key or upstream model key is issued.

Ops example: owner approval in the trusted application → signed exact proposal → read-only Ops worker → independent Ops executor → durable one-use consumption and fresh evidence checks → bounded Kubernetes patch → approved UID/desired-state verification. The executor holds no owner signing key. SQLite replay receipts use a separate new 1GiB disposable PVC; never the historical database disk.

## Cutover gates (not execution authorization)

1. Independently review the source, focused negative/legitimate tests, new trust boundaries and artifact/deployment impact. A new image lock must identify qualified v2 Financial/app/Ops/Guide subjects. Historical images cannot be silently relabelled.
2. Prepare new trusted-frontdoor, gateway-boundary and executor Secrets from fresh identities. Existing legacy secret structure is rejected for incremental onboarding. Do not reuse passwords/keys previously distributed to workers. No values belong in a report or Git.
3. Quarantine agent SQL/private-provider paths and stop legacy credential use before migration. The reviewed owner migration disables old finance logins, terminates only their sessions and revokes grants; PostgreSQL user data is preserved. The bootstrap removes legacy/unregistered LiteLLM token records before installing private boundary keys. Apply only to explicitly approved disposable/new-release targets; never the existing assessment reference cluster.
4. Deploy the new trusted services, explicit NetworkPolicies/RBAC/admission, replay storage and revised worker configuration with qualified images. Restart trusted services after credential changes: credentials are loaded at process startup, so a Secret update alone is not an activation/revocation proof. Keep every gate fail-closed; no fallback to the old direct-DB or public-provider routes.
5. Verify positive/negative auth, packet paths, stale-key revocation, signed-approval replay/restart, exact mounts/images and legitimate workflows before admitting traffic. Financial UI forwarding targets the new `apps/financial-frontdoor` Service port 8081, not the worker; Guide and console routes retain their identities.
6. Reconcile rollback explicitly. Do not re-enable compromised historical credentials or direct Ops mutation as a convenience fallback. Data rollback and retained original resources require owner review; no original state is changed here.

## Branding and compatibility

The console, dynamic browser titles, agent passports, Financial sign-in/shell and Guide page identify Agent Runtime Platform. Financial Agent, Platform Guide and Security & Operations Agent remain legitimate example names. Original GitHub URLs, internal namespaces/packages/labels, IAM/Terraform identities and image repositories remain stable. The three new trusted services, two DB roles, private provider Service/port and replay PVC are security-required additions, not cosmetic namespace migrations.

New UI/docs/Guide prompt changes are baked-image inputs and require new signatures/attestations when a future build is authorized. Mounted gateway entry code, SQL migration and generated ConfigMap suffixes are separate runtime subjects; an image signature does not authenticate them. Historical qualification hashes are never recomputed to bless different content.

Live GKE cases completed: 0/40. Source fixes and local tests do not establish live closure. Paid provisioning, billing/IAM, real SDP, artifact build/sign/push and original-cluster access remain unauthorized.

The historical `make up` driver is deliberately blocked before cloud calls in this source. It resizes the original cluster and cannot safely coordinate this migration; do not add only an image-lock flag and treat that as a cutover. Prepare an explicit target-bound rendered bundle and reviewed owner runbook after artifact qualification. Per-user workers add two replicas versus the old shared worker; include their requests and the new 1GiB replay volume in capacity/cost and cleanup inventories. No namespace is renamed for branding.

For a future authorized existing-data cutover, provide an independently reviewed existing username-to-canonical-UUID map with `platform_secrets --finance-user-directory PATH`. This contains identifiers, not password hashes. The generator binds per-user worker credentials/routes to those IDs and creates no replacement user passwords. Bootstrap preserves existing IDs/password hashes and rejects any mismatch or missing pre-existing user. Without that map, fresh synthetic provisioning generates new IDs; it must not be used to rotate an existing-data deployment. No original user directory was read in this assessment.
