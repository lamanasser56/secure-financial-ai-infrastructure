# UI redesign: live screenshots (13 October 2026)

Taken on the live platform through the private port-forwards, with headless Chromium at 1280 px. Clean demo run on
13–14 October 2026: images from commit `01376fe` (pinned in `58ff6f4`; awaiting-approval stage, one sequence per incident, Arabic amounts, Arabic explanation); the demo user's expenses were replaced with
`make seed-demo` (September 2026: 8 expenses, 1001.89 SAR; October 2026: 9 expenses, 830.49 SAR, including one
prompt-injection merchant). One fault (`make fault F=wedge`) shows a real incident; no approval was given. The agent
answered "830.49 SAR" for October in English and Arabic and "1001.89 SAR" for September. All data is synthetic.

## About — guided tour, step 1

| English | العربية |
| --- | --- |
| ![About — guided tour, step 1 (EN)](en-1-about-tour.png) | ![About — guided tour, step 1 (AR)](ar-1-about-tour.png) |

## About

| English | العربية |
| --- | --- |
| ![About (EN)](en-2-about.png) | ![About (AR)](ar-2-about.png) |

## Security & Operations — status board and a live incident (fault-demo wedged; proposal waiting for the owner)

| English | العربية |
| --- | --- |
| ![Security & Operations — status board and a live incident (fault-demo wedged; proposal waiting for the owner) (EN)](en-3-operations.png) | ![Security & Operations — status board and a live incident (fault-demo wedged; proposal waiting for the owner) (AR)](ar-3-operations.png) |

## Security & Operations — Security tab (live checks + attack-suite checks)

| English | العربية |
| --- | --- |
| ![Security & Operations — Security tab (live checks + attack-suite checks) (EN)](en-4-security.png) | ![Security & Operations — Security tab (live checks + attack-suite checks) (AR)](ar-4-security.png) |

## Financial Agent — sign-in

| English | العربية |
| --- | --- |
| ![Financial Agent — sign-in (EN)](en-5-financial-signin.png) | ![Financial Agent — sign-in (AR)](ar-5-financial-signin.png) |

## Financial Agent — guided tour after the first sign-in

| English | العربية |
| --- | --- |
| ![Financial Agent — guided tour after the first sign-in (EN)](en-6-financial-tour.png) | ![Financial Agent — guided tour after the first sign-in (AR)](ar-6-financial-tour.png) |

## Financial Agent — live answer (gemini via redaction and gateway), how we know, privacy check

| English | العربية |
| --- | --- |
| ![Financial Agent — live answer (gemini via redaction and gateway), how we know, privacy check (EN)](en-7-financial-answer.png) | ![Financial Agent — live answer (gemini via redaction and gateway), how we know, privacy check (AR)](ar-7-financial-answer.png) |

## Financial Agent — My expenses (November 2026)

| English | العربية |
| --- | --- |
| ![Financial Agent — My expenses (November 2026) (EN)](en-8-financial-expenses.png) | ![Financial Agent — My expenses (November 2026) (AR)](ar-8-financial-expenses.png) |
