# Known limitations

The items under **Cloud configuration**, **Runtime** and **Worker VM** come from the 13 October 2026 security
review; **Redaction coverage** and **Trust model** were added after it. The owner chose not to fix them for this portfolio, so they are
recorded here as accepted limitations. The platform runs on demand (`make up`, then `make down`) and will
be torn down at the end of the portfolio period. Each item gives the risk and what would close it.

## Cloud configuration, deliberately not changed

| Item | Current state | Risk | What would close it |
| --- | --- | --- | --- |
| Data Access audit logs | Not enabled on the project or its parent. Admin Activity logs are always on. | Reads of the state bucket, service-account token minting, DLP and Vertex AI data-plane calls leave no Data Access trail. | Enable `DATA_READ`/`DATA_WRITE` for Cloud Storage, IAM Credentials, DLP and Vertex AI after a cost review. |
| Application-layer Secrets encryption | GKE `databaseEncryption` is off. Google's default encryption at rest still applies. | A read of etcd storage outside the API server would see Secret values. Google's storage encryption still protects the disks. | Encrypt Secrets with a Cloud KMS key (Terraform and IAM change). |
| Alerts and backups | No alert policies. Postgres snapshots are taken only at `make down`, with no schedule and no restore drill. | A failure while the platform is up goes unnoticed. Recovery is unproven. | Readiness and audit-sink alerts, a snapshot schedule, and a recorded restore drill. |
| Audit log bucket retention lock | 30-day retention, not locked. **Deliberately not locked:** a lock cannot be undone and would block the planned teardown. | An identity with bucket admin rights could shorten retention. | Lock it only on a long-lived deployment. |
| Actions SHA pinning | Every workflow pins actions by full commit SHA today. The repository setting that would require it is off. | A future unpinned action would not be refused. | Turn on "Require actions to be pinned to a full-length commit SHA" and restrict the allowed actions. |

## Runtime

| Item | Current state | Risk | What would close it |
| --- | --- | --- | --- |
| Per-user token and DLP ceilings | Counted in process memory. A turn is checked once, then charged after each call. Missing or invalid usage is charged as the per-call maximum. | A restart, concurrent turns or a multi-call turn can exceed a per-user ceiling. The gateway key's budget ($5 per month for the Financial Agent) still caps cost. | Reserve the worst case before each call, in a shared ledger. |
| Durable audit before mutation | Audit events go to stdout and are collected by Cloud Logging. Expense inserts and ops patches do not wait for the audit write. | A crash between the change and the log line loses that audit record. | An outbox table for expense writes; record ops intent before the patch; refuse changes when the audit sink is unhealthy. |
| Redactor shutdown | The redactor runs as PID 1 without a SIGTERM handler. | During a shutdown it keeps serving until the 30-second kill. This affects availability only. | A SIGTERM handler that stops the server. |
| Login throttle and revocations | Kept in memory. A restart rotates the session epoch, so cookies issued before the restart stop working. Failed-sign-in counts restart from zero. | After a restart, an attacker gets a fresh set of attempts. | Persist the failure counts in the database. |

## Redaction coverage (added after the review)

| Item | Current state | Risk | What would close it |
| --- | --- | --- | --- |
| Person names are not redacted | The qualified entity set (Sensitive Data Protection context + the deterministic email layer) has no person-name category. | A name typed into a question reaches the model provider as written. | A person-name category in the qualified set and a live requalification ([claims matrix](../agent-platform/claims-matrix.md), recorded limitations). |
| Passport numbers are not masked (INFO-7) | The qualified category set (`SUPPORTED_ENTITIES`, hash-bound) has no passport category. | A passport number reaches the model provider as written. | Add the category to the qualified chain itself, then a live DLP requalification and a rebuilt, signed, attested and pinned redactor image ([the proper fix](realistic-data-review-2026-10.md#known-limitations-info-7-and-info-8)). Deferred because that requalification is out of scope before teardown. |
| IDs of unknown kind are masked but not reported (INFO-8) | A 10-digit value after an ID label whose first digit is not 1 or 2 is masked as `SAUDI_ID_UNKNOWN`, which is outside the qualified set. | The value is masked, but the reported categories and the privacy panel do not list it. | The same fix as INFO-7. |

## Trust model: the agent's code is trusted

The platform boundaries (network, admission, Pod Security, no API token, the gateway key's alias, budget and rate) hold
even against a hostile onboarded agent. Every item below holds only while the agent's own code behaves, because the
control runs inside the agent or the shared service does not tell agents apart. Today the platform runs only the
owner's own two agents with synthetic data, and only one of them has data.

| Item | Current state | Risk from a hostile agent |
| --- | --- | --- |
| Redaction bypass | Redaction runs in the platform client libraries (`RedactorClient` with `DeterministicEmailRedactor`; `platform-guide/src/clients.js`). The agent's NetworkPolicy allows the gateway on port 4000 (`platform/core/kubernetes/agents/financial.yaml:182-195`, `GATEWAY` in `platform/core/src/agent_platform/onboarding.py:38`), and the gateway (`programs/gateway_entry.py`, `programs/gateway_hooks.py`) does not check that text was redacted. | It calls the gateway directly with its own key and sends unredacted text to the model provider; its key budget still caps the cost. |
| Shared database credentials | Every agent that declares data receives the same `finance_web` and `finance_agent` credentials (`platform/core/src/agent_platform/platform_secrets.py:73-79`). Only one data agent exists today. | A second data agent would hold the same roles: it could call `finance.login_lookup` (a user's ID, display name and password hash by exact username, `finance.sql:41-46`) and, by setting the user ID, read the first agent's users' expenses. |
| RLS trusts the caller's user ID | The policies compare rows with `finance.user_id` (`platform/core/database/finance.sql:29-32`), which the agent's own connection sets per transaction (`platform/agents/financial/finance_agent/store.py:79`). | It sets any user ID and reads that user's rows. |
| Controls inside agent code | Tool registry, dispatch and limits, output admission, per-user token and DLP ceilings (`Limits` in `finance_agent/agent.py:288-317`) and audit events (`agent_platform/audit.py`) all run in the agent's process. | It skips them; the platform does not observe the skip. |
| Shared Postgres | One instance serves the agents and the gateway's own database (`platform/core/kubernetes/policies/network.yaml:95-105`). The roles have no connection limit, and `statement_timeout` is a role default (`finance.sql:53-54`) that a session can change. | It exhausts connections or runs long queries, and the gateway and the other agents fail with it. |
| Shared redactor and gateway capacity | The redactor has one Sensitive Data Protection budget for all callers (hourly window and daily ceiling, `programs/redactor_server.py:24` and `:54-103`) and one thread per connection (`:199-200`). Gateway keys are limited to 20 requests per minute and 2 parallel requests each (`programs/bootstrap.py:162-164`), but no per-agent connection limit is configured; how the gateway behaves under a connection flood is unverified. | It uses up the shared redaction budget (every caller then gets `redaction_unavailable`) or floods the shared services. |
| DNS | The agent may query kube-dns (`financial.yaml:159-174`). Whether public names resolve is **unverified**: the attack-suite egress probe tests a TCP connect only (`platform/clouds/gke/attack_suite.py:467-469`). | If public names resolve, DNS queries could be a data exfiltration channel. Unverified. |

**Proper fix (future work).** Move these controls out of agent code into trusted services: per-agent database roles
behind a data broker that sets the user ID itself; redaction in the gateway path (agents reach only the redactor, which
forwards to the gateway, or a gateway pre-call check), with an attack test; a tool broker; an audit collector with
closed schemas; connection and rate limits per agent at Postgres, the redactor and the gateway; and DNS restricted to
internal names. **Deferred:** the platform stays down until the 6 November 2026 teardown, runs only the owner's own
agents with synthetic data, and the redaction change alone would change the qualified redactor/gateway path
(hash-bound policy, new images, signing, live requalification).

## Worker VM (outside the platform)

`secure-infra-worker` is a VM from before Phase E. Nothing in the current platform, its manifests, Makefile, CI or
evidence depends on it; only historical documents mention it. On the owner's decision it was **stopped on 13 October
2026** (status `TERMINATED`, boot disk kept). It is deleted at teardown
(`docs/evidence/governance-and-worker-2026-10-13.json`). The default network's SSH firewall rule remains until
teardown, but no running instance is behind it.
