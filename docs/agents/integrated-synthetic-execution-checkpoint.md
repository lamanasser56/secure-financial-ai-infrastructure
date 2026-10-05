# Consolidated synthetic live-demo execution checkpoint

**BLOCKED; no new live authority requested or recorded.** A runnable two-agent
application now composes actual LiteLLM, PostgreSQL, fixture identity, tool
authorization and durable journals. Its bilingual free-text UI uses stub model and
simulated redaction. The fixed live catalog is a separate server-controlled Job;
it never replaces that conversation flow or the standing original UI.

## Exact prepared subjects

Bind the final commit in the private handoff; baseline is
`fbe5ed70a4d70f1e255d9e9851740092f41aa90d`. The
[service qualification record](../../evaluation/agent-composition/service-qualification.json)
binds every copied image input, generated client/engine inventory, reproducible
archives, fresh SBOM/scans and zero-exception policy. Registry manifests/signatures
for these three services do not yet exist. Configuration identities are:

| Service | Qualified configuration | Fresh vulnerabilities |
| --- | --- | --- |
| Gateway | `sha256:1ad99f1d6a570088e4254a711bb817430be9e3d9cb3484d285a74990776bafde` | 0 HIGH/CRITICAL; 16 MEDIUM, 8 LOW |
| Application | `sha256:bdd568e4a4a38065694dd3c5e8b7c604d52f5a10c23fd156ca2fe4b6176222b0` | 0 HIGH/CRITICAL; 16 MEDIUM, 8 LOW |
| Database | `sha256:58ee07cf0cd4256e3719d4e51e230d1d7c26369002cc2e65050881557abbaa0b` | Zero reported vulnerabilities |

The database retains PostgreSQL 17.11 and permanently uses UID/GID 70. Only its
unused `gosu` executable was removed after the unchanged base failed policy.
Its inherited entry point calls that executable only in its root branch:
[official entry point](https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh).
Original rejected scans remain evidence. No exception or severity suppression.

Reuse the historical signed SDP image at
`sha256:667ceec4b8290df1341a91a7685ad140319fca6d23f92b9948dddf9fac64136b`,
configuration `sha256:23245487ba8c7bfd616e15ff827fdfa85884dd5d15295240dd1035e22b55b90a`,
only for its unchanged SDK/adapter/policy bytes. New catalog, bridge, bootstrap,
supervisor, staging and probe programs are hashed separately in the rendered
bundle. An image signature does **not** sign these supplied programs. No new WIF
condition or workflow identity is implied.

Only the [four fixed catalog entries](../../evaluation/agent-composition/synthetic-demo.json)
execute, in order: alpha infrastructure English, alpha finance Arabic, beta
infrastructure Arabic, beta finance English. Catalog hash:
`acc96ad5016b93345a98edf67c3cf960f92e79d0bf211f1081e59cf2dfa3523b`.
No browser input, upload, alternate month, text/case/file selector or tenant override.

Prepared alias `secure-financial-chat` routes only to
`vertex_ai/gemini-2.5-flash`, us-east1, in the exact existing project. The
[route configuration](../../deploy/local-agents/litellm-vertex.yaml) disables
retries, fallbacks, telemetry and raw message/spend logging. The official
[lifecycle table](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions)
currently lists retirement on 20 October 2026. Reverify exact regional availability,
lifecycle and prices before approval/execution; stop if unavailable or retired.
Do not substitute a model or region automatically.

## Admission, accounting and failure handling

The separately reviewed [catalog program](../../scripts/run-synthetic-live-catalog.py)
requires an exact private operator admission, processor decision, explicit fixture
issuer acceptance, qualified catalog redaction evidence and distinct acknowledgement
before constructing transports. Current preparation supplies none of that live
admission. Source/program/catalog/configuration hashes and expiry are checked.
An exclusive fsynced marker and committed closed reservations precede external
work. Failure/restart never clears reservations or authorizes replay.

One catalog Job/Pod, deadline 900 seconds; at most 16 model reservations, eight per
subject; 12 read-only tool dispatches; **87 redaction inputs / 174 content SDK
attempts**, including failures, zero metadata SDP calls. The bridge reserves both
possible SDK slots before each accepted request and never refunds unused slots;
actual attempts remain separately measured. This is a stricter proposed live bound
than the local rehearsal's 128 simulated redactions. Shared input/output budget
524,288 UTF-8 bytes, 4,096 bytes per redaction, RPC three/combined eight seconds,
gateway HTTP eight seconds, prompt 4,000 bytes/output 1,024 tokens. Existing
four-model/four-tool/60-second turn and conversation limits remain.

All application/SDK/proxy/Job retries, fallbacks and automatic recreation are zero.
Stop on first control, provider, audit, byte/deadline/budget or terminal failure.
Retain only finite codes, scope, identity references, counts, timing and verified
subjects. No prompt, findings, spans, response bodies, exception messages or
credentials in retained evidence. A pass grants no provider promotion or retirement.

## Credentials, database and audit

Two explicitly admitted fixture subjects use signed JWTs, pinned public keys,
server grants and trusted tenant UUID mapping. This is fixture issuer authority,
not actual external-issuer qualification. Four scoped virtual clients are issued
once through the operator-only master key: one subject/profile each, only the chat
alias/route, maximum one parallel request, RPM32/TPM32768, 15-minute expiry. No app
mount or environment contains master/salt, issuer private key, ADC or model key.
The application has no cloud GSA and no metadata/provider egress.

Separate non-superuser/non-bypass gateway and tenant-read database roles use the
[locked official generated DDL](../../deploy/local-agents/litellm-schema.sql) and
[synthetic tenant schema](../../deploy/local-agents/tenant.sql). FORCE RLS,
transaction-local server tenant settings, parameterized SQL, rollback before
lease delivery and close/discard behavior remain. No production records, financial
write tool, `documents.read` grant or invented production table.

Tool admissions and explicit v3 terminal events commit before dispatch/delivery;
v3 identifies the candidate SDP/Vertex providers honestly. Legacy Presidio-specific
v1 traces are neither exported as provider-neutral evidence nor relabelled.
Private SQLite journals are bounded at 256 events/2 MiB each. The SDK bridge has
its own fsynced two-slot reservation ledger. No automatic tool replay. Local
persistence does not establish remote retention, tamper resistance or atomic
PostgreSQL/SQLite execution.

The [gateway supervisor](../../scripts/supervise-synthetic-demo-gateway.py) stops
its sole owned child on database failure, deadline or private-log capacity. It
never restarts it after restoration. Actual local database-pause tests stopped the
proxy in 7.55 seconds with zero prohibited upstream requests; server HTTP outage
status is not independently qualified. Native process/quarantine readback remains
a gate. Raw gateway logs stay in bounded private tmpfs and are not downloaded.

## Exact proposed cloud and Kubernetes inventory

Use only the existing private project/bucket, resolved in the private handoff.
Reuse the 15 identity-root resources, retained disabled node GSA and current states.
Recreate the same eight temporary cluster resources: dedicated VPC/subnet, NAT
address/router/subnet-only NAT, temporary minimum node-system binding, us-east1-b
cluster and sole node pool. Exact REGULAR `1.35.8-gke.1225000`, private
`e2-standard-2`/20 GiB pd-balanced, default-pool removal, Dataplane V2/FQDN,
Shielded/GKE_METADATA, kube-dns/no NodeLocal and existing control-plane contract.

The [prepared additional Terraform root](../../infra/gcp/agent-synthetic-demo/README.md)
enumerates six proposed resources, requiring new approval:

| Resource | Exact subject | Disposition |
| --- | --- | --- |
| API contract | `aiplatform.googleapis.com` | Verify/reuse enabled service; retain shared API. |
| Model GSA | `google-agent-demo-model` | Gateway only; delete. |
| Custom role | `agentDemoPredict` | Only predict/serviceusage permissions; delete. |
| Project role binding | Model GSA to custom role | Remove. |
| Gateway impersonation | `google-agent-demo/google-agent-demo-gateway` to model GSA | Remove. |
| Redactor impersonation | `google-agent-demo/google-agent-demo-redactor` to existing SDP GSA | Remove; existing evaluation binding retained. |

Total proposed inventory: **30 Terraform resources plus retained state bucket**.
New backend prefix `portfolio/agent-synthetic-demo-identity`; Terraform 1.16.5 /
Google 8.5.0. No release WIF, registry policy, billing, worker/MASAR identity or
standing-service change. Successful complete native saved plans and refresh review
remain required before mutation. No old refresh waiver carries over.

The [exact renderer/validator](../../scripts/render-synthetic-demo-bundle.py)
enumerates one Namespace, five KSAs, one fixed configuration ConfigMap, three
standalone Pods (database/gateway/redactor), three ClusterIP Services, quota/limit,
seven standard network policies, two regional FQDN policies, scoped NetworkLogging
and six suspended Jobs (three probes, two bootstrap phases, one catalog). Apply in
reviewed stages, not the whole List at once. Three-Job/six-Pod quota requires
removing probes/privileged bootstrap Jobs before the next stage. All restart
policies Never; no Deployment automatically replaces failed processes. Native
schema/admission and exact readback are mandatory.

Five fixed native-created Secrets: `database-owner`, `bootstrap-admission`,
`gateway-admission`, `redactor-admission`, `application-admission`. Values are
independently generated privately during approved execution; no credentials are
rendered or committed. The fixed staging init copies projected files into owned
0600 admission files. Bootstrap schema/client phases run once each; private app
handoff is copied natively without stdout, then privileged bootstrap workloads and
Secret are deleted before the catalog is created/unsuspended. Catalog ACK and
redaction/processor/identity decisions remain separate mandatory admission.

Memory emptyDirs: database 256 MiB/socket 8 MiB; admission 1 MiB, state 32 MiB,
temporary 64 MiB per service. Nonroot, read-only root, no escalation, drop ALL,
RuntimeDefault; no host access, public listener, Secret in app environment,
Kubernetes RBAC, PVC or production namespace. Writable temporary storage is an
explicit new demo contract, not the historical SDP Job's zero-volume contract.

Application allows only proxy, tenant DB, redactor and cluster DNS. Gateway allows
DB/DNS/metadata and regional Vertex; redactor only DNS/metadata and regional SDP.
DB admits only reviewed peers and no egress. Native probes must establish verified
TLS/HTTP2/metadata-email for the two service GSAs, genuine unrelated-route denies
and application metadata/Vertex/SDP denies. Correlate every required ALLOW/DENY
with native datapath evidence/UID-KSA-source-destination-time. Timeout alone is
insufficient. Delete probes and verify quota empty before bootstrapping.
DNS-derived IP/port rules do not isolate Layer-7/shared-IP APIs or queried names;
project workload-pool reuse is not cluster identity isolation. These limits persist.

## Single future execution sequence and cleanup

1. Review qualified service/program/configuration subjects and remaining decisions.
   Do not issue live admission until redaction and processor/fixture authority pass.
2. Fresh native inventory/version/model/price/IAM/private-state/registry checks;
   complete saved identity/creation plans and exact refresh review. No billing change.
3. One separately approved publication of the three qualified service archives to
   immutable `agent-demo-gateway`, `agent-demo-application`, `agent-demo-database`
   paths in the existing registry. Existing native operator authorization only;
   no broadened release WIF or new GitHub workflow trust. Reproduce/verify config,
   resolve/pull or verify all manifest/config/layer bytes, fresh digest-linked
   scans/SBOM/policy and exact-digest signing/verification. If native operator
   keyless signing is chosen, explicitly bind its actual issuer/identity; do not
   claim GitHub workflow/source extensions. No stored signing key or blind retry.
4. Apply only exact reviewed creation/identity saved files; record partial creation
   clock. Native schema/admission/network probes, owned source/identity readbacks
   and genuine datapath correlation. Stop on unknown/failure and clean up.
5. Start DB and schema-bootstrap once; delete schema-bootstrap after receipt. Start
   supervised gateway; issue four clients once with client-bootstrap. Copy private
   app handoff, delete privileged bootstrap/Secret. Admit redactor and suspended
   catalog only after all controls; unsuspend the catalog once. Preserve bounded
   results/audit/image/accounting. No browser-controlled model input.
6. Revoke/delete scoped clients; retain sanitized evidence before destroying tmpfs.
   Delete owned namespace/logging/workloads, review exact cleanup plans, remove
   eight temporary cluster resources plus five temporary demo identities/bindings,
   disable retained node GSA and verify real absence including generated resources.
   Retain shared APIs, existing identities/states/registry policy and evidence.

No USD5 threshold, billing screenshot or trial-credit prerequisite. New approval
accepts only this fixed demo's cost; no assumed credits or billing cap. Recheck
regional SKUs; include transient default pool, model/SDP, storage/transfer/log/NAT.
Two hours from first partial creation; cleanup begins by minute90 or immediately
on failure. No automated cluster expiry; owner takes over after disconnect. Job
TTL is not cluster cleanup. Download new artifacts before expiry; retain sanitized
subjects/admission/plan/network/result/audit/cleanup evidence privately 90 days.
Remove task credentials/raw plans/state copies/backend caches after retention;
preserve platform auth, historical work, original UI/dirty checkout and MASAR.

## Remaining blockers tied to next actions

1. **Redaction:** frozen campaign is not qualified (59 passes/context-060 FAIL).
   Approved four comparisons remained unrun after creation supervision failed;
   cleanup is verified. Do not retry automatically. Review that stop and require
   a new bounded execution decision before another attempt. Keep amount-field
   acceptance, 26 unmeasured boundaries and both historical UNKNOWN causes intact.
2. **Authority:** processor/location/independent review and explicit fixture issuer
   acceptance are pending. Complete those decisions for this catalog; no real
   issuer, production database, broad detector accuracy or Saudi residency claim.
3. **Native deployment/provenance:** local subjects and exact manifests are ready;
   registry signatures, successful cloud plans, native service/quarantine/schema/
   network and current Vertex eligibility remain execution gates. Bind them in
   one exact approval; unknown or failed gates stop without substitution/retry.

No automatic full campaign, live-agent enablement, provider-authority change,
Presidio remediation/deletion/retirement or valid-identifier research. If no
provider is qualified, keep live agents disabled and preserve offline conversation.
Historical state-read/version/IAM-delta/impersonation/signed-URL/worker-credential/
bootstrap-node UNKNOWNs and owner-self-review limitations remain. Zero scans do
not prove universal credential protection; no production or full-CS6 conclusion.
