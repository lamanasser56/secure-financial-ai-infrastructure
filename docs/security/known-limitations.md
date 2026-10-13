# Known limitations (security review, 13 October 2026)

The 13 October 2026 security review produced these items. The owner chose not to fix them for this portfolio, so
they are recorded here as accepted limitations. The platform runs on demand (`make up`, then `make down`) and will
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

## Worker VM (outside the platform)

`secure-infra-worker` is a VM from before Phase E. Nothing in the current platform, its manifests, Makefile, CI or
evidence depends on it; only historical documents mention it. The teardown plan removes it, and the owner decides
whether to stop it earlier.
