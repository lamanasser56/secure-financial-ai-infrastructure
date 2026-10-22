# Debugging the platform

A one-page guide to finding why something failed, written to be used without an AI. Every code and command below is
copied from the code, with the file and line where it is set. **Unverified** marks anything not checked against code
or a live run.

Short paths: `fa/` is `platform/agents/financial/finance_agent/`, `ap/` is `platform/core/src/agent_platform/`.
`kubectl` means the pinned binary with the private kubeconfig, as in the [demo runbook](operations/demo-runbook.md)
(section 2). Every audit line is one JSON object on stdout with `audit_event` and `component` (`ap/audit.py`).

## 1. How a request flows (Financial Agent, `POST /api/ask`)

| Step | What happens | Owning file |
| --- | --- | --- |
| 1. Entry | Host, Origin, session and CSRF checks, then the turn | `fa/server.py:103-131` |
| 2. Request ID | A new 32-hex ID, bound to the whole turn | `fa/agent.py:335`, `ap/request_context.py:13-24` |
| 3. Client redaction | Identifiers masked in the client, then the redactor is called; any failure stops the turn | `ap/redaction.py:69-100`, `fa/agent.py:421-423` |
| 4. Redactor | `POST /redact` → Sensitive Data Protection; 200, 403 or 503 | `ap/programs/redactor_server.py:160-183` |
| 5. Gateway | LiteLLM, alias `secure-financial-chat`, the agent's own key; one `gateway_request` line per completed call | `fa/agent.py:239-256`, `ap/programs/gateway_hooks.py:44-62` |
| 6. Tools | Read-only tools; the connection sets `finance.user_id` from the session, then RLS filters rows | `fa/agent.py:451-460`, `fa/store.py:76-80` |
| 7. Grounding | Every figure and record claim in the answer is checked against tool results | `fa/agent.py:436-442` |
| 8. Audit | One `finance_turn` line, the same fields as the response's `trace` | `fa/agent.py:356-359` |

The Platform Guide follows the same steps without a database, in Node.js (`platform/agents/platform-guide/src/agent.js`, `clients.js`).

## 2. Symptoms

| Symptom | Component | Code as it appears | Where it is set | Look here |
| --- | --- | --- | --- | --- |
| Answer refused | agent (in-memory limits) | `finance_turn` `outcome` `refused`, `reason` `rate_limited`, `token_budget_exhausted`, `question_length` or `language` | `fa/agent.py:300`, `:302`, `:341`, `:343`, `:353` | `kubectl -n agent-financial logs deploy/agent \| grep finance_turn` |
| Answer blocked: `redaction_unavailable` | client or redactor | `finance_turn` `reason` `redaction_unavailable`; redactor line `redaction_failed` with `reason` (exception class) and `diagnostic` (`code`, `stage`, `rpc_status`) | `fa/agent.py:423`, `:446`; `ap/programs/redactor_server.py:181-183` | `kubectl -n platform logs deploy/redactor \| grep redaction_failed` |
| … `diagnostic.code` `RESIDUAL_VALUE` or `MALFORMED_RESPONSE` | redactor (SDP result check) | the redactor's own fail-closed check rejected the result; nothing is returned | `runtime/phase3/google_sdp_adapter.py:33-38`, `:278`, `:306` | seen live for raw text sent without the client layer ([corpus note](evidence/redaction-corpus-live-2026-10-20-note.json)) |
| … `diagnostic.code` `BUDGET_EXHAUSTED` (stage `budget`), or `reason` `RuntimeError` with no diagnostic | redactor budget | 174 SDK operations per hour, 1740 per day, shared by all callers | `google_sdp_adapter.py:161`, `:173`; `redactor_server.py:24`, `:101` | wait for the next window; the daily ceiling resets after 24 h |
| … no redactor line at all | client, or redactor not reached | the client's own 15-minute budget (stage name `presidio_anonymizer` is historic and means "the redaction step"), or the redactor is down or unreachable | `ap/redaction.py:72-73`, `:82-84` | `kubectl -n platform get pods`; attack case `financial_redaction_down_no_model_call` shows the down case |
| First call after a long idle fails | redactor gRPC channel | a `too_many_pings` line in the redactor log would mean the keepalive is too eager; none seen live | `redactor_server.py:25-33` (keepalive 60 s, rebuild after 120 s idle) | [keepalive record](evidence/redactor-keepalive-2026-10-20.json) |
| Redactor answers 403 | redactor admission | `redaction_rejected` `reason` `admission`; body `ADMISSION_REJECTED` | `redactor_server.py:163-166` | wrong path, key, content type, or a chunked body |
| Answer blocked: `model_unavailable` | gateway | any non-200 from the gateway, including the key's budget, 20 requests per minute and 2 parallel requests; a refused call has no `gateway_request` line | `fa/agent.py:251-252`; `ap/programs/bootstrap.py:162-164` | `kubectl -n platform logs deploy/gateway --since=10m`; LiteLLM's own error text is **unverified** |
| Answer blocked: `model_reply_incomplete` | gateway reply | `finish_reason` was not `stop`, or no text | `fa/agent.py:255-256` | a truncated reply; retry |
| Answer blocked: `ungrounded_numbers` or `ungrounded_claim` | grounding | a figure or a record claim not found in the tool results | `fa/agent.py:440`, `:442` | by design |
| Answer blocked: `tool_unavailable` | tools or Postgres | any tool error, including a database error | `fa/agent.py:458-459` | `kubectl -n platform logs statefulset/postgres` (message text **unverified**); `statement_timeout` is 2 s (`platform/core/database/finance.sql:53-54`) |
| Rows missing, no error | Postgres RLS | rows are visible only when `finance.user_id` matches; none when it is unset | `finance.sql:29-32`; test `platform/core/tests/test_finance_db.py:76-78` | check that the session's user is the expected one |
| Sign-in fails | agent web API | 401 `wrong_username_or_password`; 429 `too_many_attempts` (5 failures per username, 20 per address); 401 `sign_in_required` (also every cookie after a restart) | `fa/server.py:148`, `:143`, `:91`, `:114`; `fa/auth.py:88-95` | wait, or sign in again after a restart |
| Request refused with 403 | agent web API | `host_rejected`, `origin_rejected`, `csrf_rejected` | `fa/server.py:83`, `:106`, `:116` | open `http://127.0.0.1:8081/`, not `localhost` |
| A Pod cannot connect | NetworkPolicy | connection times out; allow and deny decisions are logged | `platform/clouds/gke/kubernetes/gke.yaml:57-62`; `kustomization.yaml:25-29` | where the deny log lands in Cloud Logging is **unverified** (never read back live); `make attack` case `egress_containment` (`platform/clouds/gke/attack_suite.py:494-515`) |
| Pods are not created | Binary Authorization | ReplicaSet event `FailedCreate` with "image policy" or "binary authorization"; ops finding `ADMISSION_DENIED`, owner action `DEPLOY_ATTESTED_IMAGE` | `ap/ops/diagnose.py:16-17`, `:54-57` | `kubectl -n <namespace> get events --field-selector reason=FailedCreate` |
| Ops action refused by the API server | ValidatingAdmissionPolicy | reason `Forbidden` and one of four messages; the ops agent records `ADMISSION_REJECTED` | `platform/core/kubernetes/policies/admission.yaml:51`, `:60`, `:66`, `:76`; `ap/ops/agent.py:211-212` | `kubectl -n ops logs deploy/ops-agent \| grep ops_denied` |
| Approval refused (front door) | app | browser: `APPROVAL_DENIED`; audit `ops_approval_refused` with `stage` and `reason`: `passphrase_mismatch`, `not_pending`, `approval_unknown_or_used`, `request_mismatch`, `approval_expired` | `ap/app.py:304-305`, `:318-319` | `kubectl -n apps logs deploy/app \| grep ops_approval_refused`; type the passphrase with the English layout |
| Approval refused (ops agent) | ops agent | `ops_denied` `code`: `UNKNOWN_OR_USED_REQUEST`; `SIGNATURE_INVALID`, `CLAIMS_INVALID`, `EXPIRED_OR_STALE`, `BINDING_MISMATCH:<field>`, `ALREADY_USED`; `TARGET_REPLACED`, `EVIDENCE_CHANGED`, `OBJECT_CHANGED`; `CONFLICT_OBJECT_CHANGED` | `ap/ops/agent.py:169-171`; `ap/ops/approval.py:79-90`; `ap/ops/agent.py:184-190`, `:206-209` | the target changed or the approval was used: wait for the new proposal |

Ops audit names are `ops_` plus the stage (`ap/ops/agent.py:46`): `ops_denied`, `ops_failed` (codes `OBSERVE_<status>`,
`ARGUMENTS`, `SCALE_OUT_OF_BOUNDS`, `API_<status>`), `ops_approved`, `ops_executed`.

## 3. Follow one request ID

The ID is in the `/api/ask` response as `request_id`, and in its `trace` (`fa/agent.py:357-358`). The same ID appears on
`finance_turn` (agent), `redaction` and `redaction_failed` (redactor) and `gateway_request` (gateway). A value that is
not exactly 32 hex characters is dropped, never logged (`ap/request_context.py:22-24`, `gateway_hooks.py:44-45`). For
one answered turn, expect a `redaction` and a `gateway_request` line per model call, then one `finance_turn`.

Logs Explorer query (the field names come from the audit sink filter, `platform/clouds/gke/terraform/module/audit.tf:15`;
the cluster name from `platform/clouds/gke/demo_check.py:23`):

```text
resource.type="k8s_container"
resource.labels.cluster_name="agent-platform"
jsonPayload.request_id="<REQUEST_ID>"
```

The same from a terminal (**unverified**: standard `gcloud` syntax, not run from this repository):

```bash
gcloud logging read 'resource.type="k8s_container" AND resource.labels.cluster_name="agent-platform" AND jsonPayload.request_id="<REQUEST_ID>"' \
  --project=<PROJECT> --freshness=1d --format='table(timestamp, jsonPayload.component, jsonPayload.audit_event)'
```

The audit lines are also kept for 30 days in the log bucket `agent-platform-audit` (`audit.tf:7-15`).

## 4. Practice

1. `make demo-check`: read-only, one PASS or FAIL line per check, exit 1 on any FAIL (`platform/clouds/gke/demo_check.py:2-14`).
2. `make up`, then `make port-forward` and open the **Ops** screen.
3. Break the demo target (`platform/clouds/gke/lifecycle.py:246-263`) and find the finding in the Ops screen and in
   `kubectl -n ops logs deploy/ops-agent | grep ops_diagnosed` (`ap/ops/diagnose.py:13-17`):

   | Command | Expected finding | What the agent does |
   | --- | --- | --- |
   | `make fault F=wedge` | `READINESS_FAILING` | proposes a restart; approve it, then look for `ops_executed` |
   | `make fault F=oom` | `OOM_KILLED` | no proposal; owner action `RAISE_MEMORY_LIMIT_OR_FIX_WORKLOAD` |
   | `make fault F=crashloop` | `CRASH_LOOP` | proposes a restart, which cannot fix it: the fault is in the Pod spec (`ap/programs/fault_demo.py:5-8`) |
   | `make fault F=badimage` | `ADMISSION_DENIED` | no proposal; owner action `DEPLOY_ATTESTED_IMAGE` |

4. `make demo-reset`: puts fault-demo back to its declared manifest at 0 replicas and restarts the ops agent
   (`platform/clouds/gke/demo_reset.py:3-14`).
5. `make demo-check` again: every line PASS.
