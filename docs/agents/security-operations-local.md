# Security and Operations: actual local application

The separate loopback application observes actual registered local processes,
listeners, HTTP health and root storage. Financial conversation remains on 8768;
the original offline UI remains on 8765. Arabic uses RTL, English uses LTR.
No live flag exists in the UI launcher. Model explanation is optional and uses a
scoped **local stub** client; simulated redaction is not a qualified redactor.

## Run on secure-infra-worker

Use the committed worker source and a new private state directory:

```bash
umask 077
/tmp/portfolio-integrated-agents-fbe5ed7/gateway-venv/bin/python \
  /tmp/portfolio-security-operations-4420689/final-source/scripts/run-local-operations.py \
  --state /tmp/portfolio-security-operations-4420689/demo-01 \
  --port 8769 --sandbox \
  --monitor-demo-state /tmp/portfolio-local-demo-recovery-2dae719/demo-recovered-01 \
  --security-config /tmp/portfolio-security-operations-4420689/security-inputs/config.json
```

Open worker `127.0.0.1:8769/operations.html` through an SSH tunnel. The monitored
8768 stack is **read-only**. If its recorded supervisor has changed or disappeared,
startup rejects that stale monitor registration; omit the monitor option to use
the isolated sandbox. It never discovers a replacement target from a port.

Stop with Ctrl+C, or from another worker terminal:

```bash
/tmp/portfolio-integrated-agents-fbe5ed7/gateway-venv/bin/python \
  /tmp/portfolio-security-operations-4420689/final-source/scripts/run-local-operations.py \
  --stop --state /tmp/portfolio-security-operations-4420689/demo-01
```

A stop verifies the exact recorded PID/start time/UID/command digest. It stops only
this server and its sandbox child. Audit and any uncleaned sandbox cache remain.
A failed cleanup is reported as failure. Use a different state for the next run;
there is no automatic identity refresh, budget replenishment or replay.
Detached operation may use `nohup`, closed stdin and a private output file.

## Walkthrough

1. Select **Operations**, then `current-demo` and **Observe**. Examine actual
   health/listeners/storage, evidence ID and explicitly untested request-path facts.
2. Select `sandbox-demo`. Observe the real owned orphan and its unknown supervisor
   exit cause. Propose `recover`; the existing policy requires operator approval.
3. Review action, target and evidence. Read `operator-approval.secret` privately
   from this new state and enter it in the password field. Approve, then execute
   once. The model cannot supply this capability. Verify `VERIFIED`/`OK` and the
   durable outcome. Never paste the capability into chat or a report.
4. Select `sandbox-cache`, observe, propose `clean`, approve and execute. Review
   removed allocated bytes and separately measured root available space. Other
   filesystem activity can change the root metric; it is not a billed measurement.
5. Select **Security**. The existing evaluator consumes six pinned retained files:
   exact-image scan, Cosign evidence, native verification, reviewed release receipt,
   KEV and empty exception register. It can allow that historical vulnerability
   subject only. It does not perform a fresh Cosign check, qualify redaction, or
   manufacture an allow for the current application.

## Registered targets and protected data

The initial write backend supports **process-only demo stacks** and small flat
public disposable caches. Docker/containerd/RAM/VM resources are not inferred from
ports. The integrated Docker demo can only be monitored by this backend. Recovering
an entire Docker stack requires a separately reviewed resource adapter; this UI
cannot perform that deletion.

A private 0600 `--registry-config` can register additional server-owned IDs at
startup. Browser/model requests cannot register paths, processes or shell commands.
The closed registry format is implemented by
[registered_targets](../../runtime/agents/operations_local.py). Process records
must come from explicit creation: PID, start ticks, UID and command integrity,
with `resource_scope=process_only`. The supervisor must be absent before recovery.
Live member identity is rechecked immediately before PIDFD SIGTERM. There is no
SIGKILL fallback or automatic restart. A surviving service produces `FAILED`.

Cache registration pins the complete device/inode/size/time/block inventory and
asserts `content_class=public_disposable`. Its private directory must be named
`disposable-cache`. Only the closed public-cache filename set is admitted, up to
32 files, 8 MiB/file and 64 MiB total. Source, archives, models, dependencies,
credentials, audit and other filenames, directories, symlinks, hardlinks or changed
inventories are rejected. Active FDs, mappings, working directories and incomplete
process visibility deny cleaning. The fixed read-only `/proc` helper uses existing
operator sudo; mutation itself is unprivileged. No arbitrary elevated command is
accepted. Private ownership assumes one trusted local operator; these checks do
not create isolation from a malicious process with the same UID.

## Controls and budgets

Existing JWT verification/server grants, tenant resolution, injection assessment,
tool metadata/policy evaluator and exact-bound approval verifier are used. The
local fixture operator lasts 30 minutes and authorizes only operations actions.
Targets are tenant bound. Approval lasts 180 seconds, binds action/target/current
evidence/request/subject/tenant, and is consumed once. Current state must still
match. A policy denial cannot be overridden by model output or browser fields.

Per run: 64 observations, 256 KiB evidence, four actions, 64 mutation steps, four
stack members, 20 seconds/action, 4096 log bytes and zero retries. Budgets/expiry
are shown in the UI. Raw logs are untrusted; only finite indicator codes survive.
They are observations, never an instruction or a confirmed cause.

SQLite admissions commit before each mutation, and outcome commits before a
verified result is delivered. Audit failure latches writes off; deterministic
read-only observation remains available. A retained/reopened journal cannot start
another mutation run. Failed/partial actions are not replayed. Private SQLite is
local persistence, not remote immutable retention or hardware power-loss proof.
The dashboard exposes its 256-event and 2 MiB-per-file capacity alongside the
target, proposal, action, byte, model and expiry limits.
Explicit launcher shutdown still cleans up only the sandbox child it created;
that owned lifecycle cleanup is separate from approval-controlled remediation.

Optional `--model-config` admits only the existing local-stub configuration with a
scoped infrastructure client and explicit expiry. Four invocations, eight-second
HTTP deadline, eight simulated redactions/32 KiB and zero retries apply. Model
output is displayed as untrusted explanation and cannot enter action registration,
policy or approval. Missing/expired gateway admission leaves monitoring available.
Actual local LiteLLM authorized/invalid/revoked/tool-protocol/outage checks are
retained separately; they establish stub enforcement, not live model behavior.

The [consolidated live checkpoint](operations-live-execution-bundle.md) proposes
only three fixed nonpersonal synthetic facts. It requires new exact approval and
native gates. It does not replace the free-text offline conversation or qualify
its redaction. Presidio remediation and valid-identifier research remain paused.
