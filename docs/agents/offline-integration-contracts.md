# Independent offline integration contracts

## Status and authority

These are **unwired offline candidates**. No factory, UI, provider selection,
gateway image, identity grant or database migration selects them. The frozen
campaign retains 59 actual mandatory passes and the context-060 acceptance miss;
ten mandatory cases and sixteen unsupported observations remain unmeasured.
The separately approved four-comparison diagnostic cannot qualify that campaign
or conclusively resolve its historical cause. Presidio remains authoritative;
remediation and valid-identifier research remain paused. Vulnerability-blocked
Presidio is not a qualified live rollback.

Reuse the [identity/gateway preparation](identity-and-gateway-preparation.md) and
[email comparison bundle](../security/google-sdp-email-diagnostic-execution-bundle.md).
Every external model call must pass through LiteLLM; applications use scoped
clients, never gateway administrative keys or direct provider credentials.

## Canonical tool protocol

[Protocol admission](../../runtime/agents/protocol_preparation.py) accepts exactly
one complete assistant content response, index zero, finish reason `stop`.
Absent/null function and tool-call fields are valid in the
[locked LiteLLM Message contract](https://raw.githubusercontent.com/BerriAI/litellm/v1.104.0/litellm/types/utils.py).
Non-null native/legacy calls, parallel choices, chunks, refusals, truncation,
mixed call/content and unsupported message fields block. Native tool dispatch is
not implemented; adding it requires a reviewed mapping through the same registry
and governance, not automatic SDK execution.

Content goes to the qualified redaction boundary before canonical interpretation.
The separate decision admission requires the closed `{summary, classification}`
envelope, duplicate-free JSON and existing decision/tool-input schemas. Unknown
tools, injected tenant arguments and invalid periods block. Accepted proposals
still require identity, tenant, injection assessment, policy, approval where
required, and committed audit. The helper cannot prove content was redacted;
trusted composition must enforce that prerequisite. English/Arabic/mixed fixture
responses measure admission only, not actual proxy/model behavior.

The existing `HttpLiteLLMGateway` consumes the first content choice without checking
finish reason/native-call fields. The candidate prepares a stricter future
integration gate; it does not change that adapter. Future wiring must qualify
actual locked-proxy serialization, bytes, redaction order and sanitized accounting
of responses rejected after HTTP.

## Scoped-client lifecycle and denials

Reuse `ScopedCredential`, `ScopedHTTPGateway` and shared `RunAttemptBudget`.
The checked handle supplies the actual HTTP key. Wrong profile, expired/revoked
handle, administrative/provider environment or wrong alias blocks before HTTP.
Rotation revokes the old handle first and constructs a new gateway with the same
budget. Dispatched failures consume attempts; conversation reset does not reset
the run budget. Process restart is not durable accounting; local revocation is
not server revocation.

The prepared operator issuance shape remains one hour, approved alias/route and
bounded rate/token/budget. No key is issued here. Actual database-backed proxy
scope, wrong-route/model denial, expiry, rotation and deletion must be verified
without forwarding to a model. The earlier actual proxy probe returned
`No connected db.`; that is not 401/403 enforcement proof. See the
[official virtual-key contract](https://docs.litellm.ai/docs/proxy/virtual_keys).
Do not substitute a master key or custom-auth bypass for that unresolved gate.

## Trusted identity and tenant/database contract

Reuse fixed issuer/audience/public-key snapshot, locked JWT verification,
server-side subject/profile grants, pseudonymous references and local revocation.
Stale or unknown public keys fail closed. Invalid claims, issuer, audience, profile
and cross-tenant context also block. Local RSA fixtures do not qualify a real issuer,
rollover, persistent revocation or production login.

[Database preparation](../../runtime/agents/database_preparation.py) specifies one
bounded read from the existing **reference documents schema**. It re-resolves and
authorizes claims before database access, maps the resolved tenant through a
trusted server UUID directory, begins a read-only transaction, sets tenant context
transaction-locally, and parameterizes tenant/document IDs. Missing, ambiguous or
malformed rows block. Rollback occurs on success/failure; rollback failure blocks
the result and requires discarding the lease. Cursor replay proves grammar and
denial order, not database enforcement.

`documents.read` is a proposed consumer contract, **not a new grant**. Existing
agent JWT grants do not authorize it. No expenses table is invented or reference
database wired into financial tools. Financial DB integration needs its own
reviewed schema and deterministic minor-unit calculations. Before use verify an
exclusively leased connection, bounded statement timeout, read-only nonowner/
NOBYPASSRLS role, FORCE RLS and real two-tenant/unset-context/pooled-session tests.
Static SQL and an optional skipped RLS integration test do not qualify deployment.
Owner/bypass behavior is documented in [PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).

## Durable sanitized audit prototype

[Local audit preparation](../../runtime/agents/audit_preparation.py) stores only
existing validated tool-governance events. It enforces a private 0700 directory,
0600 regular single-link files, closed directory inventory, 256-event ceiling,
4096-byte event and two-MiB file bounds. SQLite DELETE journaling/synchronous FULL
are selected; synchronization is read back. Commit precedes success. Duplicate
IDs, capacity, invalid fields, corrupt history and commit failures block. Reopen
in a fresh process validates retained events. No raw prompt/argument/output/error/
credential field, silent drop, automatic pruning or retry is introduced.
The prototype remains unselected by `TraceCollector` and tools.

Local persistence tests do not prove encryption, tamper resistance, remote
retention, failover or hardware power-loss durability. FULL synchronization relies
on VFS/OS/storage behavior described by [SQLite](https://www.sqlite.org/pragma.html#pragma_synchronous).
A same-user attacker is outside this prototype's protection. Production needs
access/retention/capacity policy, durable delivery and reviewed failure ordering.
Event commit and dispatch are not atomic; an admitted event after disconnect
does not prove execution/completion. Future finite terminal receipts must not
automatically replay tools.

Trace v1 has Presidio-specific stage labels. Preserve historical v1 and consumers;
do not label SDP execution as Presidio. Review a provider-neutral v2 with honest
provider/mode, generic redaction stages and finite codes before integration. This
milestone changes neither trace schema nor `RedactorClient`/`RedactionResult`.

## Concrete next milestone: offline trusted composition

1. Review diagnostic evidence and decide finite-policy/unsupported-input scope.
   Redaction remains unqualified while mandatory requirements are unresolved;
   no amount exemption or context-060 acceptance change is implied.
2. Resolve processor/privacy/location and independent-review contracts. Freeze
   trace v2, durable audit delivery and terminal-event semantics.
3. Compose these interfaces in an isolated offline candidate with simulated
   redaction/model fixtures. Verify signatures, denial before dispatch, tenant
   confinement, canonical tool governance and audit failure. No UI live switch,
   provider authority, fallback or model call follows.
4. Derive shared SDK accounting from every question/history/model-prompt/tool/
   final-result boundary and repeated turns. Failed invocations consume budget.
   Four-model/four-tool turn and eight-turn/16-model/12-tool conversation limits
   are not two-call redaction budgets. Test UTF-8 bounds before every boundary;
   never truncate sensitive text to bypass a limit.
5. Freshly qualify changed service image inputs and prepare a separate exact
   deployment/key/database/issuer/network proposal and zero-model proxy denial
   milestone before considering bounded synthetic end-to-end agents.

Actual proxy/model protocol, real key/identity/database enforcement, qualified
redaction, latency and durable audit remain gates. No cloud deployment/key issuance
or live agent is covered by these offline candidates. Authority, consumer inventory,
qualified rollback or live-agent disable path, and Presidio retirement require
separate explicit decisions. No diagnostic pass or fake grants them.
