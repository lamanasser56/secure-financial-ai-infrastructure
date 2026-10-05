# Integrated local two-agent application

This application actually composes the existing agent core, cryptographically
verified fixture JWT identity and server grants, tool governance, scoped LiteLLM
HTTP clients, PostgreSQL tenant transactions and private SQLite durable journals.
The upstream model and redaction are explicitly simulated. Live mode is disabled.
The original free-text offline UI remains a separate, unchanged running service.

## Worker commands

Run on `secure-infra-worker`, from the final isolated source checkout:

```bash
cd /tmp/portfolio-integrated-agents-fbe5ed7/final-source
/tmp/portfolio-integrated-agents-fbe5ed7/gateway-venv/bin/python \
  scripts/run-qualified-local-agents.py \
  --python /tmp/portfolio-integrated-agents-fbe5ed7/gateway-venv/bin/python \
  --state /tmp/portfolio-integrated-agents-fbe5ed7/demo-fixed-01 \
  --database-archive /tmp/portfolio-integrated-agents-fbe5ed7/qualified-database.tar.gz \
  --user alpha --port 8768
```

The state path must be new. Open worker loopback `127.0.0.1:8768` through an
existing SSH tunnel; no firewall or public listener is required. `beta` selects
another fixed synthetic tenant at startup. Neither identity nor tenant is supplied
by browser request fields. The original UI on port 8765 is untouched.

The launcher loads only the hash-verified, freshly qualified PostgreSQL archive
into a separate 2 GiB RAM Docker/containerd store. It changes no standing daemon
or retained image/cache. A nonroot read-only database runs on an internal local
network with bounded tmpfs data/socket storage. Separate gateway and nonowner
read-only tenant roles use SQL generated from the locked official LiteLLM schema.
The proxy issues four model/route restricted clients, one per subject and profile.
The app receives no master key, issuer private key or direct provider credential.

Fixture identities expire in 15 minutes; local proxy keys expire in one hour.
The free-text application shares at most 32 gateway reservations per launch and
16 per subject across both profiles, sessions and conversation resets. A financial
turn normally uses three and an infrastructure turn four. The 900-second run
deadline, shared redaction budget and smaller turn/conversation limits also apply.
Starting a new conversation does not replenish the launch budget. There is no
automatic retry, budget increase or credential refresh after a blocked turn.
Ctrl+C stops the owned proxy/stub/UI and destroys its database/network/RAM store.
Private audit remains. No automatic refresh or restart exists.

To stop the same launch from another worker terminal:

```bash
cd /tmp/portfolio-integrated-agents-fbe5ed7/final-source
/tmp/portfolio-integrated-agents-fbe5ed7/gateway-venv/bin/python \
  scripts/run-qualified-local-agents.py --stop \
  --state /tmp/portfolio-integrated-agents-fbe5ed7/demo-fixed-01
```

Run one integrated stack at a time: its gateway and stub use fixed loopback ports
4001 and 8767. Startup checks these ports and the selected UI port before creating
the RAM runtime or credentials. It verifies the listeners belong to its recorded
children before issuing clients or advertising UI readiness. A busy port blocks
startup without stopping its owner. Port 8765 is reserved for the original UI.

The stop command verifies the private launcher record, PID start time, source and
exact state argument before signalling. Each owned cleanup phase is attempted
even when another fails; `launcher-status.json` reports bounded stage and cleanup
codes. Private service logs and audit remain in the state directory. The command
does not recover states created by the older launcher without an ownership record.

For a fixed four-input rehearsal, use a new state and replace the final UI options
with `--rehearse`. For actual proxy/database integration checks use `--check`.
These options launch, exercise and clean up their own local stack. They make zero
external model or SDP calls.

The rehearsal admits only the [committed catalog](../../evaluation/agent-composition/synthetic-demo.json).
Its fsynced exclusive start marker blocks reuse after success or failure. It shares
16 model reservations, eight per subject, 128 redaction operations, 524,288 UTF-8
input/output bytes and a 900-second deadline across both profiles and tenants.
Existing per-turn and conversation limits remain. There is no live flag, arbitrary
text/file selector or automatic retry. The free-text local UI is not this catalog.

## Actual integration and boundaries

Actual worker tests passed authorized/invalid/deleted-key and admin/model-scope
proxy checks, English/Arabic agent runs, two tenant totals, missing-tenant denial,
sequential transaction isolation and write denial. Native tool calls, truncation
and cross-profile proposals block tool dispatch. Audit admission failure prevents
tool dispatch; terminal commit failure prevents delivery. Every completed DB lease
rolls back and closes. These results use an actual local server/database and a stub
upstream; they do not qualify Vertex, real issuer authentication or redaction.

The locked proxy emits optional provider metadata. Admission accepts only absent,
empty, or null-refusal metadata; actual refusals, other metadata content, duplicate
JSON fields, native/legacy tool calls and truncation remain blocked. This follows
the [locked LiteLLM message contract](https://raw.githubusercontent.com/BerriAI/litellm/v1.104.0/litellm/types/utils.py).
The canonical JSON proposal still passes redaction, registry validation, trusted
identity/tenant authorization and audit admission before dispatch.

Durable v1 tool events record governance admission, not proof of execution. Closed
v3 turn events commit before delivery and identify simulated redaction/stub model.
They contain no transcript, arguments, result bodies, provider errors or credentials.
V3 adds finite terminal stage/reason and distinct runtime invocation, budget
admission/denial, HTTP attempt/response and successful/blocked trace counts.
Historical v2 rows remain readable and are never assigned invented failure codes.
The local model trace contract is v2; the original phase3 v1 contract is unchanged.
Download reports are v2. `model_requests` still counts runtime invocations, including
one refused by a control before HTTP. `simulated_model_requests` uses measured
HTTP attempts when available; `model_invocation_attempts` preserves the invocation
count. Attempt, response and stub counts do not establish external provider receipts.

For the shared subject limit, the blocked report exports
`terminal_failure={stage:litellm,reason:subject_attempt_budget_exhausted}`.
Total-run exhaustion, run deadline and unavailable client credentials have distinct
finite reasons. Unknown exceptions export only `agent/required_control_failed`.
No exception message, raw HTTP body or credential enters a report. Failed trace
admission and terminal commit continue to block delivery; no partial answer is
delivered after a terminal journal failure.
SQLite durability is local; remote retention, tamper resistance and atomic execution
across PostgreSQL/SQLite are unqualified. No automatic tool replay exists.

## Qualification and next execution checkpoint

The [retained service qualification](../../evaluation/agent-composition/service-qualification.json)
binds its historical exact input files, two matching archives per service, configuration identities,
fresh scans/SBOMs and the unchanged zero-exception policy. Application/gateway have
zero HIGH/CRITICAL, 16 MEDIUM and eight LOW findings; the derived PostgreSQL image
has zero reported vulnerabilities. Actual nonroot startup/RLS passed. The database
removes only the unused root-switch executable and retains PostgreSQL 17.11; original
failed base-image scans are preserved. No scanner exclusion or package-policy waiver.

Qualification used isolated worker RAM stores after disk-capacity failures; no old
work/cache/image was pruned and no worker disk was resized. Actual local enforcement
used the locked host interpreter and real qualified database. Service-container
imports/native engine/default entry points passed; a full containerized proxy/agent
network deployment is a future native gate. No registry publication/signature is
claimed for these new services.

The terminal-diagnostic repair changes application runtime and contract inputs.
The retained application image qualification does not qualify those new bytes.
The host-interpreter local demo can be verified independently with the unchanged
qualified database and locked proxy. Fresh reproducible application image builds,
SBOM, vulnerability/secret scans and exact source binding are required before a
revised service-image execution checkpoint; no old manifest/signature is substituted.
The gateway and database subjects remain unchanged. Updating source does not patch
an already running process; coordinate its stop, retain its audit, then start from
the reviewed new checkout with a fresh state. Never overwrite a running checkout.

The [execution checkpoint](integrated-synthetic-execution-checkpoint.md) binds the
fixed catalog, prepared Vertex route, credentials, operation bounds and cleanup.
It is blocked before approval/execution until redaction, processor/identity/model decisions and native provenance/network
admission pass. The running local application remains usable independently.
Presidio remains authoritative; Google SDP is not promoted or wired into live agents.
Presidio remediation and valid-identifier research remain paused.
