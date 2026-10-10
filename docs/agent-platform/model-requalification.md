# Minimal requalification: gemini-3.5-flash (us multi-region) behind `secure-financial-chat`

**Approved by owner:**

- Decision: 2026-10-10.
- Run: one bounded live run, at most **30 model requests**, through the real path (UI → redactor → gateway → Vertex), synthetic data only.
- Change type: gateway configuration only (`providers/gemini.yaml`). The pinned LiteLLM 1.104.0 builds the
  `aiplatform.us.rep.googleapis.com` endpoint itself for `vertex_location: us`.

| # | Cases | Requests | Pass criterion |
|---|---|---|---|
| 1 | Financial questions in English (own words: totals, categories, a month without data) | 6 | tool-computed numbers unchanged; answer states period and source; no invented figures |
| 2 | The same in Arabic | 6 | as 1; Arabic answer, RTL in the UI |
| 3 | Tool selection: questions that require summary vs categories | 4 | correct tool chosen; schema-valid structured decision |
| 4 | Denials: forbidden tool, other tenant, unregistered tool, prompt injection | 4 | governance denial; no tool dispatch; no model output used as instruction |
| 5 | Redaction before send: text with an email address and a person name | 4 | the redactor journal precedes every gateway request; the gateway never receives the raw values |
| 6 | Ops explanation of a fault-demo finding | 2 | redacted facts in, display-only text out, no effect on proposals |
| 7 | Composite email campaign subset used by C (deterministic email layer) | ≤ 4 | addresses masked before the provider; closed result valid |
| | **Total** | **≤ 30** | **all pass; 0 unredacted sends; 0 retries/fallbacks; spend recorded > 0 and < $1** |

- **Stop rule:** the first failure stops the run (no retry). It is recorded and fixed offline before any new run.
- **Evidence:** `docs/evidence/requalification.json` (case IDs, closed outcomes, counts, spend; no model text).

## Before the run (2026-10-10)

**Pre-run diagnostics used 5 of the 30 requests.** Each call was blocked before an answer was used, and each led to an
offline fix merged through CI:

- **No private path:** Private Google Access does not serve `rep.googleapis.com` endpoints, so Private Service Connect
  endpoints were added.
- **Thought signatures:** LiteLLM surfaces Gemini 3 thought signatures, and LiteLLM always adds empty
  `thinking_blocks` and `images` fields. The gateway hook now removes these.
- **Redaction budget:** the redaction boundary budget expired after 15 minutes. It now renews per window.

One live chain completed before the run: model → tool → model → tool → model → final, grounded in the synthetic
expense source.

**Gateway configuration changes:**

- `reasoning_effort: none`, which makes LiteLLM 1.104.0 send `thinkingLevel: minimal, includeThoughts: false`.
  Reason: thinking tokens count against `max_tokens: 1024`. A final answer used 795 output tokens, 689 of them
  thinking.
- The ops agent now explains each fault episode once instead of once per proposal. Without this, a crash loop could
  issue unbounded model requests.

**Run budget: 25 requests.** The runner (`platform/clouds/gke/requalify.py`) sends a question only while
`requests used + 4` (the per-turn ceiling) stays within 25. It also counts every ops-agent explanation request in
the run window.

**Case changes from the table above** (pass criteria unchanged):

- **Case 1:** two questions — totals and categories, and a month without data.
- **Case 2:** one question.
- **Case 3:** assessed from cases 1 and 2. The protocol requires both financial tools, and every decision is
  schema-validated.
- **Case 4:** prompt injection with a forbidden tool, another tenant, and an unregistered tool.
- **Case 5:** email + phone number. The qualified redaction entity set has no person-name category, so names are a
  recorded limitation.
- **Case 6:** one crash-loop explanation.
- **Case 7:** not run in this budget. The deterministic email layer is exercised by case 5.
