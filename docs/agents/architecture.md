# Agent architecture and limits

## Shared trust boundary

```mermaid
flowchart TD
    A[CLI or private UI] --> B[Trusted startup identity and profile]
    B --> C[Closed input schema and authorization]
    C --> D[Existing policy and Presidio redaction]
    D --> E[Phase 3 runtime: LiteLLM boundary]
    E --> F[Untrusted structured decision]
    F --> G[Canonical registry and complete Phase 4 governance]
    G --> H[Allowlisted read-only handler]
    H --> I[Closed output schema, minimization and Presidio]
    I --> E
    F --> J[Validated final answer and cited tool facts]
```

The offline test double replaces only the gateway client seam and analyzer/anonymizer service seams. The core uses the same validation/governance coordinator as the repository runtime. There is no alternative tool registry format, policy engine, approval bypass or direct provider connection.

## Contracts and dispatch

The canonical [agent registry instance](../../contracts/agents/tool-registry.json) is loaded by the existing Phase 4 registry validator. Five tools bind to exact committed input/output schemas. Swapping a schema reference, enabling a write, requiring an approval, changing an action/risk/version or selecting a tool outside the profile fails closed. The read-only policy implements the existing Phase 3/4 interfaces in `runtime/phase4/tool_policy.py`.

| Profile | Registered tool | Required action | Result |
| --- | --- | --- | --- |
| Infrastructure | `read_ci_summary` | `diagnostics.ci` | Approved synthetic scenario evidence |
| Infrastructure | `read_image_summary` | `diagnostics.image` | Synthetic qualification summary |
| Infrastructure | `read_runbook_section` | `diagnostics.runbook` | Approved bounded suggestion |
| Financial | `expense_summary` | `expenses.summary` | Tenant/period aggregate |
| Financial | `expense_categories` | `expenses.categories` | Deterministic ranked category aggregates |

All metadata describes read-only internal tools, with two-second operation limits and one execution per tool per run. Arguments select enum sections or a validated month. They cannot select files, URLs, commands, tenant identifiers, credentials, schemas or provider configuration. Paths are code-selected, bounded and reject symlinks. The core calls the authoritative governance coordinator, then checks its trusted tenant against the run's tenant before dispatch. Qualification alone remains insufficient for execution outside this coordinator.

Model decisions use the closed [decision schema](../../contracts/agents/decision.schema.json), encoded inside the existing Phase 3 `summary` string. The original `{summary, classification}` gateway response contract stays intact. Unknown keys, invalid tool IDs, schema violations, duplicate dispatches, fabricated evidence IDs, wrong agent/period and suspected injection block the run. Tool results are validated, assessed, minimized and redacted before another model call. Final answers are also redacted and revalidated. Valid evidence references do not establish the semantic accuracy of every model-written statement; authoritative calculations are shown separately as tool facts.

## Identity and isolation

`DemoIdentity` is explicitly simulated authentication. A startup operator chooses `demo-alpha` or `demo-beta`; separate agent instances receive only their profile's actions. A private ephemeral bearer stays inside the process. The tenant reference is a 16-character keyed HMAC pseudonym; raw fixture tenant IDs do not enter prompts, results, audit events or browser configuration. The financial handler obtains its tenant exclusively from the governance-qualified server context.

For live integration, inject a real authenticator, resolver and authorizer. The live factory rejects simulated identity and refuses a client credential equal to a provided gateway master credential. This equality check cannot independently establish the role of an arbitrary key; gateway-side scope qualification is required. Offline startup requires an explicitly offline gateway; request content cannot enable simulation or live mode.

## Bounded execution

| Boundary | Default maximum |
| --- | --- |
| Model requests / tool dispatches | 4 / 4 per run |
| Overall run | 60 seconds |
| Each complete model stage | 20 seconds including its runtime controls |
| Each tool / governance / identity operation | 2 seconds |
| Standalone redaction operation | 10 seconds |
| Core message / assembled model prompt | 500 characters / 4,000 UTF-8 bytes |
| Tool/final JSON before and after redaction | 4,096 UTF-8 bytes |
| Private UI request / core response | 4,096 / 32,768 bytes |
| HTTP adapter response | 65,536 bytes |

Limits can be reduced at trusted startup and cannot be expanded. No automatic model, tool or evaluation retry exists. POSIX main-thread interval timers interrupt operations; the core refuses execution in a background thread or while another interval timer is active. The UI therefore uses a single-thread server. An integration must preserve this execution model or separately qualify an equivalent cancellation boundary. These in-process deadlines do not undo a remote operation already accepted by a server; initial tools are strictly read-only.

The existing HTTP adapters reject redirects and ignore ambient proxy settings, avoiding silent credential forwarding/rerouting. Inputs cannot select an endpoint. The private UI binds only to `127.0.0.1`, validates exact Host and same-origin POST requests, rejects forwarded/identity headers, requires a per-browser session CSRF token, disallows uploads/chunked/oversized bodies and serves only fixed assets. It uses CSP, no-store, no-referrer, nosniff and DOM text rendering. It records no request logs, persists no browser data and exposes no agent/provider credential. Other processes on the same host are outside its authentication guarantee; production use requires a separately secured service.

## Conversation and bilingual presentation

The private UI sends only a closed agent profile, presentation language, bounded question, optional enum evidence source and opaque conversation handle. Server startup selects identity/provider configuration. Clarification slots are server-owned: browser history, tenant, limits, model and endpoint fields are rejected. The actual question is validated, assessed and redacted before scope recognition and the canonical orchestration. The limited offline grammar explicitly refuses unsupported text. A display projection runs after core validation and redaction; it adds no policy engine or tool permission.

A per-browser HttpOnly, SameSite=Strict cookie and independent CSRF token bind sessions. Conversation handles are additionally bound to trusted subject, scopes, raw internal tenant, pseudonymous tenant reference and profile. Every turn and tool re-authorizes. Another browser/session, profile or changed tenant cannot use the handle. This is simulated authentication; processes/users with access to the same host are not independently authenticated. Session secrets and internal context are never logged or downloaded.

Arabic RTL and English LTR catalogs provide separate selected-language views. Historical message DOM nodes retain their original text/lang/dir and are hidden in the other language view. Switching is entirely local and submits no request. Technical identifiers use LTR `bdi`/`code`; JSON uses LTR `pre`. CSS uses logical spacing/alignment. All data enters text nodes; untrusted HTML is never inserted.

Infrastructure supporting evidence consists of the synthetic CI source and approved runbook section. The invented image qualification fixture is labelled supplemental context with no current image-scan claim. Financial cards and rankings use tool aggregates; integer division and remainder with the SAR currency scale produce monetary strings. The projection rejects inconsistent aggregate/source/period/ranking results. It never derives amounts from model-written text.

Sanitized fact reports and audit traces are collapsed by default. A strict download projection excludes question text, all model prose, context/history, handles, cookies and CSRF/provider credentials. Every displayed value is DOM text. The UI distinguishes simulated model request attempts, external provider calls and tool dispatch attempts; token usage and cost remain unavailable. Redaction accounting explicitly describes synthetic service doubles, not proven live Presidio detection.

## Remaining limitations

The illustrative injection assessor matches four categories; it does not prove complete detection. Independent authorization and tool/schema containment remain mandatory. Offline redaction doubles do not prove production Presidio coverage. Audit events qualify attempted tools and are kept in memory; durable delivery is not implemented. Real user authentication, production tenant/RLS integration, real model response quality, real Arabic Presidio/model coverage, gateway key scope and live network containment remain unproven. Google SDP's separate inconclusive evaluation is not a provider-authority decision.

## Conversation limits and lifecycle

| Boundary | Maximum |
| --- | --- |
| Turns, including clarification/refusal | 8 per profile conversation |
| Model request attempts / governed tool dispatch attempts | 16 / 12 per conversation |
| Cumulative identity/core execution | 240 seconds per conversation |
| Session/context lifetime | 900 seconds from bootstrap; never refreshed by turns |
| Sessions / active conversations | 8 sessions; one per profile per session |
| Retained message context | Last 4 redacted previews, 80 UTF-8 bytes each; 512-byte JSON cap |
| Full serialized conversation response | 65,536 UTF-8 bytes; core response still 32,768 |

The manager reduces per-turn limits to remaining quotas and reserves attempted operations before invoking the core. Unknown framework failures retain reservations instead of replenishing them. Verified actual counters refund unused reservation. Identity-binding elapsed time reduces the remaining execution deadline. No retries or background work exists. An exhausted conversation requires an explicit reset; offline reset is not an account-wide/cloud budget control. The live follow-up must add authenticated identity-wide gateway limits independent of resets.

Retained previews and tool/model content are untrusted and reassessed/redacted before each model call. Validated continuation slots carry an intent and exact enum source or month; arbitrary context cannot become policy. Expired sessions are purged on access/bootstrap; an idle expired context becomes unusable immediately by its monotonic deadline and is physically removed on the next access or process shutdown. No disk transcript, browser storage or raw request log is written. Browser history is bounded to 16 bubbles per profile and cleared on reset/page reload. Context truncation deliberately sacrifices long-memory behavior.

The financial registry outputs now include a required `data_available` indicator (tool versions `2.0.0`). Unavailable fixture periods are distinguished from known empty datasets. The core stops after the summary lookup and returns only an availability notice/source/month; it never presents fabricated zero totals. Existing IDs, actions, risk classes, schemas-as-authority, permissions and deterministic arithmetic are preserved.
