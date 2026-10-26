# Current limitations and evidence scope

This describes the current boundary-v2 source. It replaces the earlier trust model that put database/session credentials and mandatory masking authority inside an onboarded worker. Older reviews remain historical evidence for their recorded revisions, not descriptions of the current code.

## Masking

**Person names and passport numbers are not masked.** Only supported identifier patterns are covered, with format and context limits. The exact eight categories and honest English/Arabic UI wording come from `agent_platform.masking_scope`; enforcement remains in the existing redaction contract. Some other labelled numeric IDs can be masked without a named category in worker metadata. A redactor call without findings does not prove the absence of sensitive content.

The trusted model boundary masks accepted messages before dispatch and keeps its private upstream credentials separate from workers' public gateway keys. A hostile worker cannot use its public key to bypass this boundary. This does not make arbitrary model output trustworthy.

## User scope and process memory

The trusted Financial frontdoor selects the authenticated user and a bound worker. The broker verifies active capabilities and selects the database identity outside the worker. Workers do not hold the old shared `finance_web`/`finance_agent` credentials. The legacy login roles are disabled by bootstrap.

Financial per-user question/token counters, Guide counters, login throttling and some service limits are held in the current processes' memory. Restarts and multiple processes are not a durable global quota. Sign-in revocations are in memory; rotating the frontdoor session epoch invalidates cookies from before its restart. There is no durable lockout promise.

Financial conversation display and drafts stay in page memory across tabs/language changes, without browser storage. Worker history is separate and bounded. A page reload loses the local display. Sign-out revokes the session and asks the worker to forget; worker unavailability can prevent that separate cleanup. Failed or lost write responses must not be presented as proof that no write occurred.

## Model output and audit

Registered tool schemas, caller scope and output admission bound what a worker can do. Pattern-based injection filtering does not recognize every instruction. Financial numeric and selected-claim checks do not establish the truth of every sentence. A worker-produced trace can report a check; it is not independent boundary evidence.

Request events are bounded metadata. Expense writes and Ops changes do not promise a durable audit record before mutation. Cloud log collection, a configured retention period and a worker trace are not proof of complete recording or irreversible retention. No durable-audit enforcement feature is claimed.

The Guide reads its declared current documentation corpus. Index version, source identity and retrieved excerpts determine the material available to it. Its model selects passage IDs; code returns only those indexed excerpts and rejects generated factual prose. Zero hits refuse without a model call. The worker trace reports source_quotes_verified, which checks literal source selection, not truth, relevance, completeness or deployed enforcement. Excerpts keep their source language; this is not generated translation.

## Shared services and cloud controls

Postgres, redactor and gateway capacity is shared. Declared connection/rate/concurrency limits reduce particular failure modes; they do not prove availability under every load or a distributed cost ceiling. Model-key budgets are separate from compute, storage and other cloud charges.

DNS resolver access is required by the declared workload paths. No general claim of blocked DNS exfiltration follows from TCP-connect tests. Pod Security, RBAC, admission and network observations each cover their own scope. A completed posture scan is a bounded comparison of declared resources, not a full security assessment.

Backups, restore drills, project-level Data Access auditing, customer-managed Secrets encryption, alert delivery and irreversible retention require their own evidence. A source declaration or a historical review is not a current cloud read-back. Snapshotting at `make down` is not a backup schedule or a proven restore.

## Release evidence

Old image pins, earlier live results, workflow identity, a receipt's source field and cryptographic source provenance are different evidence. New security code needs fresh qualification of its selected images. A build certificate must not be treated as proof of checkout source unless that source is independently bound by verified provenance. `make demo-check` and the final assessment have explicit, separate scopes.

Known follow-up: `release_verify.Verifier.provenance` parses `cosign verify-attestation` output as one JSON document, so a digest carrying more than one attestation fails verification closed until the parser reads one statement per line.

There is no “wait until teardown” justification for misdescribing current controls. Features outside the approved release scope stay honestly limited; they are not silently promised by UI wording.

## Persistent engineering VMs

`secure-infra-worker` is retained as an engineering resource; release builds use GitHub-hosted runners. `sfai-engineering` is the current isolated test VM. **Neither VM nor its retained disk is to be deleted without an explicit owner request.** They are outside disposable assessment cleanup and the GKE workload boundary. A historical teardown date does not authorize deleting them. See [retention and teardown](../agent-platform/teardown-plan.md).
