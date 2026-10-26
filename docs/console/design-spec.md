# Console blueprint design spec

One screen = one message. Use few words, with technical detail on click. Keep the original blueprint character: a dark grid, precise rules, condensed headings and restrained mint/amber status accents. Console, Financial and Guide share the source assets in `platform/core/ui`; their exact public routes are in `shared-assets.json`.

## Colors and typography

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#0C2745` | Page background |
| `--ink` | `#F2F7FF` | Main text and rules |
| `--box` | `#14406E` | Cells and selected surfaces |
| `--panel` | `rgba(18, 58, 99, 0.45)` | Quiet panels |
| `--muted` | `#9DB6D6` | Secondary labels |
| `--allowed` | `#7CF0C0` | Scoped allowed/observed states and actions |
| `--denied` | `#FFB547` | Denied/failing states |
| `--declared` | `#9CC3FF` | Declaration/inference context |
| `--code` | `#071A30` | Code/input background |

Use the 96 px major and 24 px minor grid from the canonical stylesheet. Do not add a second palette, rounded dashboard cards, glows or unrelated icon styles.

| Role | Family | Weight |
| --- | --- | --- |
| English headings, tabs, labels and cells | Barlow Semi Condensed | 700–800 |
| English prose/captions | IBM Plex Sans | 400–600 |
| Arabic headings/prose | IBM Plex Sans Arabic | 400–700 |
| IDs, digests, paths and code | IBM Plex Mono | 400–500 |

Fonts and OFL licenses are self-hosted beside the canonical assets. Use `font-display: swap`; no CDN. Mono is for identifiers/code, never the body or heading. Arabic sets real page `lang`/`dir`; technical literals retain their own direction.

## Frame and interaction

The recording viewport is 1440×900 with 40 px gutters and no centered max-width page. Small screens use 16 px gutters. Desktop header height is approximately 68 px; wrapping at small widths is deliberate. Use the shared wordmark, rule, tab treatment, controls and drawer.

Skip to content focuses the current `main#view` without changing a hash route or losing a draft. Clickable objects are real links/buttons or keyboard-operable SVG controls. Enter/Space opens the same details; Escape closes and restores the opener. Focus is visible. Respect reduced motion, pause periodic reads while hidden and clean up timers/listeners when leaving a screen. Late responses cannot repaint another screen/session.

The connection badge describes the last API outcome and browser receipt time. “API answered” is scoped to that result; after a minute show “Last response”. Network, JSON and HTTP failures are distinct. Idle time never means Offline. Limited observation sources stay labelled. The badge is not a health, posture, provenance or data-freshness verdict.

## Map

Preserve one topology presentation model and the actual allowed/denied edges. The platform column has three cells and a thin strip:

| Cell | Subtitle | Details |
| --- | --- | --- |
| Model gateway | identifiers masked first | `gateway-boundary` authenticates/validates and enforces masking; `redactor` handles supported patterns; private `gateway`/LiteLLM uses the upstream key |
| Data broker | your rows only, read-only | Trusted `financial-frontdoor` user routing/capabilities and broker-owned read-only data access |
| Approval executor | changes need your signature | Independent `ops-executor`, bound owner approval, exact mutation authority |
| Audit strip | Audit · request events | Bounded component events and their limits |

Provider and DLP connectors attach to the composite Model gateway cell. Agent lines, denial paths and animations still use actual topology data. Presentation grouping does not alter the Console API or invent a new permitted route.

The model drawer lists all three parts before the supported-pattern details. It lists exactly the supported eight categories, says explicitly **person names and passport numbers are not masked**, and explains format/context limits. A check without findings does not prove no sensitive information existed. The strip does not claim every request is completely or durably recorded.

At narrow widths, render readable vertical cells from the same model. Do not shrink a desktop SVG until its labels are unreadable. Preserve focus/detail state on resize. At 1440×900 the main drawing and its scoped explanation fit the recording frame.

## Passports and Onboard

Separate **observed**, **inferred**, **declared** and **failing** checks. Counts describe those categories. One observation cannot stamp a whole agent VERIFIED. Image admission inferred from running resources is not a cryptographic signature check.

Passport fields and health come from current APIs or show unavailable. The Onboard table is labelled **Manifest summary**. This is a read-only review, with the actual owner validation/generation workflow. The rejected example shows its real rules and expected nonzero exit. Try/return links use the supported Console/Financial/Guide local services.

## Ops

Show posture source, scan window, completeness and scope. Zero current findings requires a complete fresh scan; missing/unreadable/stale data stays unknown. Keep operation denials separate. Include every declared Financial worker and observed core target; missing/scaled-down members cannot be hidden by a logical aggregate.

The action says **Approve & execute**, with target/action/age and immediate effect clear. Refusal, expiry, unknown execution outcome and NOT_VERIFIED never become success. Preserve passphrase drafts across read-only refresh, clear submitted secrets and suppress duplicate execution. Read-only targets offer an explicit owner action. Model text is display-only.

## Financial, Guide and Break it

Financial retains visible conversation and drafts across tabs/language switches in page memory. Prevent overlapping submit paths and stale result/trace display. Keep missing cost unavailable, write uncertainty explicit and sign-out confirmation real. Application wording in both languages describes process-memory limits without a durable quota/lockout promise.

Guide uses the same shell/fonts/tokens, with component-owned question/source layout. Documentation knowledge comes only from its reviewed current corpus. Source excerpts/version and the actual admission checks must support its wording; a hit count or numeric check is not universal semantic proof.

Break it is a viewer of a selected-release/runner-bound report, not a live attack button. Separate attacks and positive controls, PASS, FAIL and NOT_EXERCISED. Missing or unqualified data has an honest empty state and no historical fallback pass.

## Verification

`tests/browser` exercises current components with explicit synthetic fixtures, including 360/1440, keyboard, reduced motion and failure recovery. HTTP tests verify canonical asset bytes and security headers. These screenshots/tests are not evidence that a selected deployment or real model turn passed; that needs the final exact-image walkthrough and assessment.
