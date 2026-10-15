# Request ID and per-request trace

Every user request gets one request ID where it enters the platform. The ID is 32 lowercase hex characters (uuid4) and
carries no user data.

| Entry point | Where the ID is created | Where it travels |
| --- | --- | --- |
| Financial Agent `POST /api/ask` | `FinanceAgent.ask` | `X-Request-ID` header to the redactor and the gateway, plus LiteLLM request metadata; returned in the response |
| App conversation `POST /api/conversation` | `RequestIdConversations.turn` (`app.py`) | the same header on redactor calls and on the gateway transport; audit lines of the agent core; returned as `request_id` |

The redactor logs `request_id` on `redaction` and `redaction_failed` lines. The gateway hook (`gateway_hooks.py`) logs one
`gateway_request` line per completed call: `request_id`, `key_alias`, `model`, `total_tokens`, `cost_usd`. A value that is
not exactly 32 hex characters is dropped, never logged.

## The `finance_turn` trace

`/api/ask` returns `trace`, and the audit line `finance_turn` carries the same fields. It is built once per turn.

| Field | Meaning |
| --- | --- |
| `request_id`, `user_ref` | the request, and the keyed reference of the signed-in user (never the user id) |
| `outcome`, `reason` | `answered`, `refused` or `blocked`, and the closed reason code |
| `model` | `alias` and the model name LiteLLM resolved (null if not reported) |
| `model_calls`, `tokens` | counts for this turn |
| `cost_usd`, `cost_source` | from LiteLLM's `x-litellm-response-cost` header per call; `null` with `unavailable` if any call lacks it; `0.0` with `no_model_call` |
| `tool_calls` | per call: `tool_id`, `rows_returned` (an aggregate total counts as one row) |
| `data_access` | when a tool ran: tools ran as the read-only role `finance_agent` under FORCE ROW LEVEL SECURITY scoped to `user_ref`. It states the data path; it never claims that row-level security refused anything |
| `grounding_result` | `grounded`, `refused` or `ungrounded_claim_blocked` |
| `redaction` | `calls` (redactor calls this turn) and `categories` with counts (redactor calls in which the category was found) |
| `injection_result` | `null`, or `instruction_like_text_withheld` with `withheld_fields` |

Never present: the question, the answer, prompts, amounts, merchant or note text, passwords, keys.

Not verified live: that LiteLLM stores the request metadata and sends the cost header on this deployment; the code
tolerates both being absent.
