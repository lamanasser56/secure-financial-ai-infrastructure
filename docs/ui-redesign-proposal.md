# UI redesign proposal

> **Superseded.** The console (Map, Agents, Onboard, Ops, Break it; see [the console design](console/design-spec.md)) replaced the About and Security & Operations pages described below. This proposal is kept as a record. To open the current pages, see [HOW-TO-VIEW.md](HOW-TO-VIEW.md).

**Status: implemented on 13 October 2026, on owner approval.** The pages live in `platform/core/ui/` (About,
Security & Operations) and `platform/agents/financial/finance_agent/ui/` (Financial Agent). To open them, see
`docs/HOW-TO-VIEW.md`; live screenshots are in `docs/evidence/ui-2026-10-13/`. The implementation differs from the text below in three ways:

- The Financial Agent is the onboarded agent with its own app on port 8081. The retired front-door Financial Agent
  is no longer shown, so About is the front door's start page.
- The two flows on About are numbered HTML step lists instead of SVG, so they read correctly in both directions.
- The `frontend-design` plugin was not available, so the work follows this proposal directly.

All security behavior stays unchanged.

## Goal

A non-technical viewer, such as a recruiter, understands within a minute what each agent does and why it is safe.
The pages are bilingual (Arabic and English), calm and clean.

## Constraints found in the code

These decide how the redesign can be built:

- **Six fixed paths.** The front door (`runtime/agents/web.py`, which is hash-bound) serves only `/`, `/app.js`,
  `/style.css`, `/i18n.json`, `/operations.html` and `/operations.js`. Each file has a hard limit of **32 KB**. New
  pages such as "About" must therefore be views inside these files (switched in place, no new URL).
- **Where the files live.** The image copies `platform/core/ui/` over `demo/ui/`. The repository's `demo/ui/*` and
  `demo/i18n.json` stay byte-identical because they are hash-bound in earlier qualification records. All new work
  goes in `platform/core/ui/` (including a new `index.html`, `app.js` and `style.css` there).
- **CSP:** `script-src 'self'; style-src 'self'; img-src 'none'`.
  - No inline scripts, inline styles or images.
  - Diagrams are inline SVG elements in the HTML.
  - Only system fonts can be used.
- **Input limit:** a question is limited to **500 characters** by the conversation contract. The assembled prompt
  must also stay under 4,000 bytes, which an Arabic question near 500 characters can exceed; the core then refuses it
  with `input_too_large`.
- **Redaction proof:** the response carries the detected *categories* for each model call (`detected_categories` in
  the model traces). Per-entity *counts* are not exposed. The proof can show "Email: masked in 3 of 3 model calls"
  without new core data. True counts would need a core change, which this proposal does not include.
- **The `frontend-design` plugin** is not installed in this environment. Either it is installed before
  implementation, or the work follows this proposal directly.

## Global elements (all pages)

- **Header:**
  - platform name: "Secure AI Agent Platform" / "منصة وكلاء الذكاء الاصطناعي الآمنة";
  - a language switch (EN | ع);
  - a "?" button that re-opens the tour;
  - links: Financial Agent · Security & Operations · About.
- **Page intro:** every page and tab has a title plus one or two sentences (texts below).
- **Guided tour:** written for this project.
  - It opens on the first visit.
  - It numbers and highlights each section with a short tooltip (Next / Back / Skip).
  - It can be re-opened from "?".
  - "Seen" is remembered in localStorage, and the page still works if storage is blocked.
- **Formatting in Arabic:**
  - Western digits 0–9 everywhere.
  - Dates like "12 أكتوبر 2026", times like "1:47 م", amounts like "240.00 ر.س".
  - Technical IDs are wrapped LTR (`<bdi dir="ltr">`).
  - Every label, event, state and error is translated, with no mixed-language labels.
- **Technical details:** raw JSON appears only under a collapsed "Technical details / تفاصيل تقنية".
- **Empty states:**
  - "No pending approvals." / "لا توجد موافقات معلّقة."
  - "No policy denials yet — denials appear here when a request breaks a rule." / "لا توجد حالات رفض بعد — تظهر هنا
    عندما يخالف طلبٌ إحدى القواعد."

## Page 1 — Financial Agent (`/`)

**Intro:**

- EN: "Ask about your expenses in your own words. The agent answers only from your own records, hides personal data
  before anything reaches the AI model, and shows how it knows."
- AR: "اسأل عن مصروفاتك بكلماتك. يجيب الوكيل من سجلاتك فقط، ويخفي البيانات الشخصية قبل وصولها إلى نموذج الذكاء
  الاصطناعي، ويبيّن مصدر كل رقم."

**Wireframe, top to bottom:**

1. **Status strip.** It shows the true live state only:
   - "Live · synthetic data · signed in as Alpha" / "مباشر · بيانات تجريبية · مسجّل الدخول: ألفا";
   - the remaining questions this hour ("12 of 16");
   - the session expiry time.
   - The stale "offline simulation" and "live mode disabled" banners are removed.
2. **Question box.** It has a 500-character counter. The hint reads: "Example: How much did I spend in January
   2026?" / "مثال: كم صرفت في يناير 2026؟"
3. **Answer card.** The answer comes first, in large text.
4. **"How we know" / "كيف عرفنا".** It lists the tools used (in plain names: "Expense totals", "Spending by
   category"), the period, and the source ("Synthetic expenses v1").
5. **"Privacy check" / "فحص الخصوصية".** Example: "Before the AI model saw your question, we masked: phone number,
   email (in 3 of 3 model calls). No personal values were sent." There are no values, only categories.
6. **Blocked or refused answers.** These show one human sentence with the reason, for example: "This question asked
   for another customer's data. The platform blocked it — you can only see your own records."
7. **Technical details** (collapsed).

**Ungrounded claim:** the answer card never shows model text that is not supported by this turn's tool results.
This depends on the feature "fix the 'invoice is recorded' claim" (numeric and claim grounding), which is done before
the redesign.

## Page 2 — Security & Operations (`/operations.html`)

**Intro:**

- EN: "This agent watches the platform's services, explains problems in plain language, and fixes them only after
  your approval. It can restart or resize a service — it can never change what a service runs."
- AR: "يراقب هذا الوكيل خدمات المنصة، ويشرح المشكلات بلغة بسيطة، ولا يصلحها إلا بعد موافقتك. يستطيع إعادة تشغيل
  الخدمة أو تغيير حجمها فقط — ولا يستطيع أبداً تغيير ما تشغّله."

### Tab "Operations / العمليات"

1. **Service cards**, one per registered service, each with a state, a short plain-language line, and a colour plus
   icon plus text (never colour alone):
   - healthy: "Healthy — no action needed" / "سليمة — لا حاجة لأي إجراء";
   - degraded: "Degraded — not ready to serve" / "متدهورة — غير جاهزة للخدمة";
   - failing: "Failing — keeps crashing" / "متعطلة — تتوقف باستمرار".
2. **Incident flow with a step tracker:** Detected → Diagnosed → Proposed → Approved → Executed → Verified.
   - **Incident card:** what happened, the evidence in plain words, and the model's explanation labelled "AI
     explanation — for information only, it cannot change the action" / "شرح الذكاء الاصطناعي — للعلم فقط، ولا
     يغيّر الإجراء".
   - **Proposed action card:**
     - the action ("Restart the service" / "إعادة تشغيل الخدمة");
     - a passphrase field;
     - an "Approve" button;
     - the note: "Your approval is valid once, for this action on this service, for 5 minutes."
   - **Execute → Verified outcome:** "Verified: the service is healthy again (1 of 1 ready)."
   - **Owner-action findings** (out of memory, image pull, admission denied): "Owner action required — no automated
     fix: [the recommendation]". There is no Approve button.
3. **Timeline.** It shows meaningful changes only: fault detected, diagnosis, proposal, approval, execution,
   verification, denial. Repeated "healthy" observations are collapsed into one line ("Healthy since 1:47 م").
4. **Human messages:**
   - "No action needed — service is healthy" replaces `ACTION_FAILED`.
   - Every denial has a reason, for example: "Approval expired — approvals are valid for 5 minutes."
   - Stale copy ("live mode disabled", "operator-approval.secret") is removed.

### Tab "Security / الأمن"

**Intro:**

- EN: "What the platform checked before running anything."
- AR: "ما الذي فحصته المنصة قبل تشغيل أي شيء."

It is a readable checklist with pass/fail per item:

- the image is signed;
- the image is attested (Binary Authorization);
- vulnerability scan: 0 high/critical;
- no public exposure;
- no internet egress;
- the agent cannot change a Pod spec;
- redaction precedes every model call.

Each item has a "how we know" line.

## Page 3 — About the platform (a view inside `/`, opened from the header)

**Intro:**

- EN: "Any team can deploy its own AI agent here and inherit these protections without building them."
- AR: "يمكن لأي فريق نشر وكيله هنا ليرث هذه الحمايات دون أن يبنيها بنفسه."

**Two inline-SVG flows:**

1. **Answer path:** You → Privacy masking → Gateway (budget, no direct provider access) → AI model → Answer checked
   against your records.
2. **Ops loop:** Observe → Diagnose → Propose → Your approval → Execute once → Verify.

**Controls in plain language**, one line each:

- Isolated network.
- Scoped AI key with a monthly budget.
- Automatic redaction.
- Tool registry with policy and approval.
- Audit trail without personal content.
- Signed images only.
- The ops agent cannot change what a service runs.

## Testing (at implementation time)

- **UI unit tests:**
  - every key exists in both languages;
  - no mixed-language label;
  - Western digits in Arabic;
  - LTR isolation of IDs;
  - empty states;
  - no `innerHTML`;
  - each file stays at or under 32 KB.
- **Screenshots:** every page in Arabic and English.
- **Delivery:** small PRs under the standing rules.
