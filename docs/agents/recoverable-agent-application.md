# Financial and Security & Operations application

The combined application uses actual LiteLLM and PostgreSQL locally. Default
reasoning and redaction are explicitly simulated. The Financial view accepts
Arabic/English wording with an explicit period; missing or ambiguous periods
produce clarification. Every financial read uses the existing nonowner role,
FORCE RLS, trusted tenant directory, parameterized SQL and transaction rollback.
Amounts and sources in the UI come from validated tool results.

## Start and stop on the worker

Use the committed checkout and locked interpreter identified in the private final
handoff. Start only with a new state, separate from all standing user services:

```bash
umask 077
/tmp/portfolio-integrated-agents-fbe5ed7/gateway-venv/bin/python \
  scripts/run-recoverable-agents.py \
  --python /tmp/portfolio-integrated-agents-fbe5ed7/gateway-venv/bin/python \
  --database-archive /tmp/portfolio-integrated-agents-fbe5ed7/qualified-database.tar.gz \
  --state /tmp/portfolio-agent-restoration-b24b233/demo-review-01 \
  --port 8770 --gateway-port 14004 --stub-port 18772
```

Open worker loopback
8770 using an SSH tunnel. The financial conversation links to `/operations.html`
on the same origin. English uses LTR and Arabic uses RTL. Ctrl+C performs owned
shutdown. From another terminal, stop the exact source/state:

```bash
/tmp/portfolio-integrated-agents-fbe5ed7/gateway-venv/bin/python \
  scripts/run-recoverable-agents.py \
  --stop --state /tmp/portfolio-agent-restoration-b24b233/demo-review-01
```

The stop command checks source, state, UID, PID start time and PIDFD. It never
adopts another launcher or kills an arbitrary port owner. Shutdown destroys only
this test database/runtime; audit and private source/configuration remain. Never
reuse a previous state. The original financial demo and Operations server remain
separate on 8768/8769, with the original UI on 8765.

## Controlled service restoration

1. Observe `test-gateway`. Diagnose its exact current evidence.
2. Propose `test_failure`. Code policy requires an exact operator approval. Read
   `application/operator-approval.secret` privately, enter it in the password
   field, approve and execute once. Never paste it into model conversation.
3. Observe again. An exited process is confirmed; its exit cause is unknown unless
   supported by evidence. Monitoring remains available during gateway outage.
4. Propose `restore`, approve that new action/evidence, execute once and inspect
   the measured readiness/listener proof and durable outcome.
5. Ask a financial question again. Recovery does not renew keys, identity expiry,
   application counters, database contents, conversation history or audit.

Only the creating supervisor registers its own gateway/stub. The adapter pins
launch recipes, source, qualified Prisma engine and credential-file hashes; checks
PID ownership, original expiry and database/quarantine immediately before starting.
There is one start attempt per service, zero retries, no signal escalation and no
request replay. A failed start consumes the attempt and returns FAILED. Health
polling is bounded by 32 checks and the unchanged 20-second action deadline.
The creating process imports the locked proxy before UI readiness. Recovery uses
that prepared code in a new owned child, closes inherited audit/database/UI file
descriptors and checks the original private recipe. This avoids a recovery-time
cold import without extending the deadline or creating credentials.

Audit admission precedes mutation and durable verification precedes delivery. Audit
failure in either the Operations journal or shared model/redaction reservation journal latches writes off; observation survives. Historical audit v1 remains
readable. Service outcomes use v2 with finite health/attempt/renewal proof. Model
text cannot register targets, approve, choose commands or change policy decisions.
The current user Docker/RAM stack is never registered for mutation here.

An operator may additionally supply `--registered-disposable-cache /exact/path/disposable-cache`
at startup. Registration freezes its inventory; no browser/model can select a path.
Only the existing flat public-cache format, ownership/link/size limits and complete
read-only process visibility are admitted. Observe its active-use/storage evidence,
propose `clean`, approve that exact evidence, and inspect measured reclaimed bytes.
Source, credentials, audit, required archives and active files are protected.
Do not register a current worker cache for a controlled demonstration.

## Visible limits and live admission

The UI displays existing conversation limits and shared subject/run model counters,
expiry, redaction bytes/operations, action and audit capacity. Shared model caps
are 32 per run and 16 per subject across financial/Ops/reset. Ops explanations
have an additional four-invocation cap. Identity/client lifetime is 15 minutes;
operations approvals last at most 180 seconds, with four actions and zero retries.
A reset or service restoration replenishes none of these.

`--trial-admission` plus `--trial-configuration` is a separate, disabled-by-default
entry to the candidate live composition. It requires an exact clean source,
program hash, owner/processor/fixture decisions, original expiry, complete frozen
70+16 live acceptance, provenance, enforced network/credential/quarantine receipts,
policy acceptance and a distinct fixed-integration PASS. A fixed-input approval
cannot authorize free text. No admission or client is issued in preparation.
An exclusive fsynced admission marker also prevents a second state from renewing
the same grant. Failed admission/startup does not authorize automatic replay.
The current failed campaign cannot pass this gate. Private receipt trust assumes
a trusted operator, not adversarial code with the same UID.

Live transports use only the scoped LiteLLM channel and authenticated redactor
channel; no application provider key/ADC/master key. Trial reservations commit
model/tool/redaction budgets before work and survive reopen. New terminal v4 and
model trace v3 name candidate SDP/Vertex honestly; legacy Presidio v1 evidence is
not relabelled. Provider handoffs do not prove exact receipts or billing. The
current worker application network/identity boundary is not yet natively qualified.
See the [single execution checkpoint](recoverable-agent-execution-checkpoint.md).

Presidio remains authoritative. Its remediation and the valid-identifier research
remain paused. A local or fixed-model pass changes no provider authority, enables
no general live agent and authorizes no retirement.
