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
