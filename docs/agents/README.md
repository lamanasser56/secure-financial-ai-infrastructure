# Bounded demo agents

Two read-only demonstrations reuse the existing secure runtime. They were built after the synthetic SDP evaluation's final cleanup checkpoint. Neither entry point restarts that evaluation or creates cloud resources. Presidio remains authoritative; Google SDP is disabled and unwired into the agent path.

## Implemented

- One bounded core composes the Phase 3 runtime and canonical Phase 4 registry, invocation, injection, policy, approval and AI-audit controls.
- Infrastructure diagnostics reads three approved synthetic CI scenarios, a synthetic image qualification summary and bounded runbook sections. It suggests repairs and executes none.
- Financial analysis uses two isolated synthetic tenant fixtures. Tools calculate integer SAR minor-unit totals, counts and category rankings. The simulated model explains those facts.
- Separate server-selected identities, policy profiles and tool allowlists. The financial profile has no infrastructure permissions.
- Runnable CLIs and a loopback-only conversation UI with separate Arabic RTL and English LTR views, keyboard-operated tabs, labelled controls, status announcements and safe text rendering. Questions and clarification replies in either language pass through the validated, redacted bounded core. Optional examples fill the question box without submitting it.
- Offline adversarial tests for request/proposal/schema containment, tenant context, redaction, evidence references, budgets, deadlines and HTTP boundaries.

**Every CLI/UI result is an offline simulation.** Authentication is simulated. The deterministic `FakeGateway` sends no HTTP request and truthfully records `provider_called=false`. The demo exercises the existing `PresidioRedactor` composition with explicitly synthetic analyzer/anonymizer test doubles. Its email pattern is not evidence of real Presidio coverage, Arabic detection, production security or model accuracy.

## Designed

The same core can compose integration-supplied real identity/tenant/authorization adapters, real Presidio services and the existing LiteLLM HTTP adapter. `prepare_gateway_core` is an integration factory; the CLI/UI expose no live mode. Both profiles would use the existing `secure-financial-chat` alias through LiteLLM. Gemini via Vertex AI is the intended gateway provider. Agents contain no direct provider SDK or Google credential handling.

See [live integration prerequisites](live-integration.md). No live provider request or cloud/IAM change was performed for this implementation.

## Integration-dependent

Real authentication and trusted tenant resolution, scoped gateway virtual keys, gateway/provider identity, qualified model/region, real Presidio service availability and language coverage, durable audit delivery, deployment networking and promotion remain separate integration gates. The UI is a private local demonstration, not a production authentication service. Model explanations remain untrusted even when they cite valid evidence.

## Run the demonstrations

Use the repository's existing locked Python 3.12 environment. No new dependency, browser package, asset CDN or build system is required.

```bash
python3 -B scripts/diagnose-infrastructure.py --scenario docker-config
python3 -B scripts/analyze-demo-expenses.py --period 2026-01 --user demo-alpha
python3 -B scripts/analyze-demo-expenses.py --period 2026-01 --user demo-beta
python3 -B scripts/analyze-demo-expenses.py  # requests a reporting period
python3 -B scripts/serve-demo-agents.py --user demo-alpha --port 8765
```

Open `http://127.0.0.1:8765` on the server's own machine. Stop it with Ctrl+C. Do not expose this service publicly or put a proxy in front of it. The user is selected at startup and cannot be switched by browser data. No credentials need to be supplied for offline operation. Do not enter real data. Type a question about the approved synthetic sources, then Send. Clarification replies continue the same conversation. New conversation explicitly clears the selected profile's ephemeral context. The language switch makes no request, executes no tool and changes no permission: earlier messages retain their original language and appear only in that language view.

Run the agent suite and complete repository gates:

```bash
python3 -B -m unittest discover -s tests/agents -p 'test_*.py'
bash scripts/check.sh
```

## Data and evidence

[CI fixtures](../../demo/fixtures/ci.json) cover archive exporter/driver mismatch, Docker configuration lifecycle and GKE default-pool/version conflict. They are synthetic examples inspired by reviewed failures, not retained operational logs or current cloud state. [Image evidence](../../demo/fixtures/image.json) is invented qualification data, not a registry-digest claim. [Runbook sections](../../demo/fixtures/runbooks.json) are bounded, suggestion-only excerpts created for these demonstrations.

[Expenses](../../demo/fixtures/expenses.json) contain two tenants and two months, no product schema or real account/customer records. For January 2026, demo-alpha totals 24,000 SAR minor units (SAR 240.00) across three expenses: Software SAR 200.00 and Transport SAR 40.00. Demo-beta totals 9,000 minor units (SAR 90.00) across two. Tool results omit raw tenant IDs and individual rows. An unavailable month returns an explicit availability limitation after one governed summary lookup. It supplies no expense facts, fabricated zero report, category result or guessed reporting period. Only January and February 2026 have fixture data.

Financial responses include the reporting period. Infrastructure responses show failure, cause, repair, supporting CI/runbook source IDs and unverified points; the invented image fixture is supplemental context, never a current scan assertion. Responses preserve actual source IDs, deterministic tool facts, sanitized pseudonymous traces and qualification-only governance events. A governance event is not proof that a tool executed successfully; `tool_executions` counts attempted dispatches, and only validated successful results enter `facts`. On a required-control failure, no partial unsafe result is returned and no operation is retried.

See [architecture and limits](architecture.md) and the [decision record](adr-001-bounded-demo-agents.md).

## UI reports and accounting

Tool facts appear as readable cards and tables. The server formats SAR amounts with the currency's defined scale of two decimal places using integer division and remainder; it never parses model text or uses floating-point arithmetic for money. Unsupported currencies fail closed. Original integer minor units and canonical audit events remain in expandable sanitized JSON and the downloadable report. Financial aggregate/source/period consistency is checked before presentation.

Each optional example can be sent again manually; there are no automatic retries. A missing or ambiguous financial month asks for clarification before any financial tool or simulated model request. Only the presentation language is browser-selected. Closed request schemas reject identity, tenant, model, endpoint, credentials, limits and history fields. The server resolves identity and binds each conversation to its browser session, trusted tenant context and agent profile.

Run accounting separates simulated model requests from external provider calls. Token usage and cost are unavailable, not estimated as zero. Simulated redaction completion with test doubles is not evidence of live Presidio detection. Reports exclude raw questions, model answers, retained context, conversation handles, session cookies, bootstrap CSRF and private startup credentials. Only closed validated fixture facts, deterministic projections and sanitized audit events are downloadable. History remains ephemeral in process/browser memory and is cleared on explicit reset, expiry or server shutdown. Downloads are intentional user-controlled persistence of sanitized facts, never transcripts.

## Free-text offline scope

This is a deterministic, limited simulation, not a general language model. It recognizes complete supported question forms and controlled clarification replies, rather than silently mapping unrelated text to a canned scenario. Unsupported questions receive an explicit simulation limitation with no model/tool request. The actual validated and redacted question remains in each orchestration prompt. The simulated model chooses only from the existing registered read-only tools.

| Question | Behavior |
| --- | --- |
| `Why did Docker archive export fail?` | Approved synthetic CI/runbook diagnosis; image fixture is supplemental |
| `How do I fix Docker configuration?` | Suggested repair; never executed |
| `What does the runbook say about GKE cluster version?` | Approved cluster-contract section |
| `Why did the release fail?` | Select an approved source or reply to the source clarification |
| `Show my expense totals and categories for 2026-01.` | Trusted tenant aggregate and ranking |
| `Show expenses` then `January 2026` | Same conversation; no financial tool before clarification |
| `اعرض مصاريفي` then `يناير ٢٠٢٦` | Same bounded financial clarification in Arabic |
| `لماذا فشل تصدير صورة Docker؟` | Arabic-input supported diagnosis; answer follows selected view |
| `Show expenses for 2026-03` | Unavailable data; no fabricated record/total |
| `Who won the match?` | Explicit unsupported offline refusal |

The date parser accepts explicit `YYYY-MM` and English/Arabic month names with an explicit year. Relative or multiple months require clarification. The UI month control only fills an optional example: it cannot silently supply a missing month to a free-text question. Evidence selectors are enums, not filesystem or URL inputs.

Each profile has at most eight turns, sixteen simulated model requests, twelve attempted tool dispatches and 240 cumulative execution seconds per conversation. The original four-model/four-tool and sixty-second per-turn bounds still apply, reduced to the remaining conversation budget. Clarifications/refusals count as turns. Context expires with the fifteen-minute browser session; at most eight sessions are held. The server retains at most four redacted message previews (80 UTF-8 bytes each, at most 512 bytes together), plus validated month/source continuation slots. Reset can replenish only this offline conversation budget; it is not a live spend or identity-wide rate limiter.

```bash
python3 -B scripts/diagnose-infrastructure.py --question 'Why did Docker configuration fail?' --language en
python3 -B scripts/analyze-demo-expenses.py --question 'اعرض مصاريفي في يناير ٢٠٢٦' --language ar
```

Technical identifiers remain unchanged. Arabic prose stays RTL; identifiers, SAR amounts, dates, URLs, commands and expandable JSON use explicit LTR bidi isolation. Earlier messages are never silently translated on a language switch. See the [conversation decision](adr-002-ephemeral-conversations.md) and the [single live follow-up bundle](live-follow-up-bundle.md).
