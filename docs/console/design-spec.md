# Console design spec

The design is **frozen**. This page is the written form of the five reference screenshots (the ★ screens) and the
design tokens. Part E builds the console from it; the data comes from the endpoints in [Data contract](#data-contract).

Screens: Map, Agents, Ask (an agent's chat), Onboard, Break it. Ops has a tab but no ★ screenshot; see [Ops](#ops).

## The rule

**One screen = one message.** Few words. Details only on click, in the Explain drawer.

- A screen has one headline (six words or fewer), at most one line of subtext and one primary action.
- A fact the screen needs is on the screen. Everything that explains *why* or *how* is behind a click.
- No paragraph on a screen. Copy that needs a second sentence belongs in the Explain drawer.
- State is never colour alone: every state has an icon and a word (✓ Verified, ✕ Blocked, ! Ignored).

## Tokens

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#0C2745` | Page background, with the grid below |
| `--ink` | `#F2F7FF` | Text, lines, outlines ("white ink") |
| `--box` | `#14406E` | Boxes: diagram nodes, passport body, list rows |
| `--panel` | `rgba(18,58,99,0.45)` | Panels: chat, "What the platform did", side cards |
| `--muted` | `#9DB6D6` | Secondary text, captions, ids |
| `--allowed` | `#7CF0C0` | Allowed, verified, live, ✓, the primary action on the Agents screen |
| `--denied` | `#FFB547` | Denied, blocked, ✕, warnings, the BREAK IT tab, the run-attacks action |

Taken from the screenshots, not in the token list (use these, do not invent others):

| Token | Approximate value | Use |
| --- | --- | --- |
| `--declared` | `#9CC3FF` | The "Declared" chip and its ✓ ring (manifest only, not seen live) |
| `--inverse` | `#F2F7FF` fill, `--bg` text | Primary buttons on the dark page (`Issue a passport`, `Send`, `Onboard`); `Run the attacks` uses `--denied` instead |

**Grid.** The page background carries a faint blueprint grid: a minor line every 24 px and a major line every 96 px,
both `--ink` at very low opacity (about 4 % minor, 7 % major). It is decoration: it never sits under text at higher
contrast than the page itself, and it is removed in forced-colours mode.

**Lines.** 1 px `--ink` at 60–80 % opacity for outlines and the header rule. Boxes have square corners. The passport
card is the one exception (a 12–16 px radius).

## Type

| Role | Family | Weight | Size |
| --- | --- | --- | --- |
| Headings, tab labels, chips, buttons, nodes | Barlow Semi Condensed | 700–800 | Screen headline 56–64 px; card title 28–32 px; panel title 20–22 px; labels 11–14 px, uppercase, 0.06–0.1 em tracking |
| Body, captions, list text | IBM Plex Sans | 400–600 | 15–16 px (captions and metadata 12–13 px) |
| Ids, digests, namespaces, code, the machine-readable lines | IBM Plex Mono | 400–500 | 12–14 px |

IBM Plex Mono is used **only** for ids, digests, namespaces, file paths, manifest text and the passport's machine line.
Never for headings or prose.

**Fonts are self-hosted** (SIL Open Font License). The `.woff2` files and their licence texts live in the repository
next to the console assets, are served from the same origin, and are never loaded from a CDN or a font service. Use
`font-display: swap` and subset to Latin. Fallbacks: `'Barlow Semi Condensed', 'Arial Narrow', sans-serif`;
`'IBM Plex Sans', system-ui, sans-serif`; `'IBM Plex Mono', ui-monospace, monospace`.

## Frame

- Full width, as the ★ screens were drawn (1440 × 900, the recording viewport): 40 px side padding and no centred
  max-width column; 16 px side gutters on small screens. Each screen fills that frame at 1440 × 900 without scrolling
  sideways or cutting anything off.
- **Header** (68 px tall) on every screen: the wordmark `AGENT-PLATFORM` (Barlow 800, tracked) and a green `● Live` badge on the left;
  the tab row in the centre; a 1 px rule under all of it. There is no `Sample data` badge: the console shows no sample data.
- **Tabs:** `MAP · AGENTS · ONBOARD · OPS · BREAK IT`. The current tab is `--ink` with a 2 px underline; the others are
  `--muted`. `BREAK IT` is always `--denied` (its underline too, when current).
- `Live` means the screen's data came from the console API in the last minute; otherwise the badge reads `Offline`.
- The Ask screen is reached from an agent (Try this agent) and has no tab of its own; it shows `← <Agent>` above the
  headline, and the AGENTS tab stays current.

## Screens

### Map ★ — "Every agent gets its own room."

Message: each agent is isolated; the platform sits between it and everything else.

- Headline right-aligned with a muted hint: `Click any part to see how it works.`
- Beside the headline, numbers from real data only: `agents` (agent nodes in `topology`) and `protected` (agents whose
  passport stamp reads VERIFIED; shown only while live checks answer and every agent's checks came back). There is no
  `blocked today`: `activity` is a short window of recent events, not a count for the day.
- A diagram on the left (the cluster panel, about 950 × 674 at 1440 × 900; agent boxes about 210 × 96, the platform block
  about 230 × 320). On the right (386 px): each agent with its health chip and `n verified · m declared`, `Live activity`
  (the last three events), and two buttons, `ONBOARD AN AGENT` and `TRY TO BREAK IT`. Explain is closed until a part is clicked.
- **Diagram.** A dashed outline `PRIVATE CLUSTER` holds the agents (left column, `--box` boxes with a name and one
  muted line, for example `python · own rows only`) and a hatched-header `PLATFORM` block (middle) with three stacked
  cells: Model gateway (`one key, one budget`), Redactor (`hides personal data`), Audit (`every request recorded`), in that
  order so the straight lines reach Google AI (top) and Google DLP (below) without crossing. Outside the outline, right:
  Google AI, Google DLP (boxes) and Internet (dashed, `--denied`, `no way out · why?`; the whole box is clickable).
- **Lines.** Allowed paths are solid `--ink` lines with a `--allowed` dot at each end. Denied paths are dashed
  `--denied` with a small `✕ why?` tag (agent ↔ agent, agent → Internet). The platform-to-Google paths carry a
  `private link · why?` tag.
- Every box, line and tag is clickable (the `✕ why?` wall chips, `private link · why?`, the Internet box, the three platform
  rows) and opens its topic in Explain (below). The selected one is outlined `--allowed`.
- **Explain on the Map** opens in the right column in place of the aside (about 420 px, same top and height as the
  drawing panel); the drawing (about 920 px) stays fully visible and is not dimmed. Close or Esc brings the aside back and
  returns focus to the part. Content: eyebrow `EXPLAIN · VERIFIED LIVE` (12 px, `--allowed`; `EXPLAIN · NOT SEEN LIVE` in
  `--muted` when `proof` is null); title (Barlow 800, 32 px); a mono line naming the layer the part rests on (for example
  `Kubernetes NetworkPolicy · GKE Dataplane V2`, fixed wording taken from the infrastructure files); `IN PLAIN WORDS`
  (16 px), `HOW IT WORKS` (15 px), `PROOF · <SOURCE>` (Plex Mono 12 px, an `--allowed` border when live), `WITHOUT IT`
  (an amber left rule); the source path in Plex Mono pinned to the bottom of the panel. Other screens keep the drawer.
- Data: `topology` for the diagram; `explain/<topic>` for the card.

### Agents ★ — "Agent passports"

Message: every agent has an identity, permissions and proof.

- Subtext: `Every agent gets an identity, a set of permissions, and proof.` Primary action top right: `ISSUE A PASSPORT →`
  (`--inverse`), which goes to Onboard.
- **Left rail** (300 px): one row per agent: a small passport cover with the agent's icon, the name (Barlow 700, 20 px) and
  the namespace (mono 12 px, muted).
  The selected row has a `--allowed` left bar and a `--box` fill.
- **Passport card** (right): a `--box` card (14 px radius, a soft shadow, a faint guilloche from CSS gradients, about
  368 px tall) with a top strip `AGENT PLATFORM` (left) and `AGENT PASSPORT · P<PLT<01` (right). Left: a framed icon tile
  (about 150 × 176) with the image digest beneath it. The icon is a simple inline line icon chosen from manifest facts,
  never from the name: shield for the platform tenant, bank for an agent over the `finance` database, book for an agent
  whose tool searches the docs, the platform emblem otherwise. The name is 40 px; the MRZ is Plex Mono 15 px, widely tracked
  (`sha256:4b1e…09cd`, mono, first 4 and last 4 hex characters). Fields in a grid (label 10–11 px muted caps, value
  Barlow 700 20 px): NAME (large), NAMESPACE, TEAM, RUNTIME, MODEL, BUDGET (`$5.00 / month`), DATA (`none`, or the database and `own rows`). The reference screens show VALID UNTIL here; no
  live or manifest source for it exists, so DATA replaces it rather than showing a made-up date. A round
  `VERIFIED` stamp (`--allowed`, rotated about −8°, text `CHECKED LIVE`, `n / 8 GUARANTEES`) sits top right. Along
  the bottom, a two-line machine string in Plex Mono (the "MRZ"), decorative, built from the agent's name and the
  guarantee initials.
- The Security & Operations Agent has a passport too. It is a platform tenant (namespace `ops`), not onboarded from an
  `agent.yaml`: its facts come from its own manifests (Deployment, registry, NetworkPolicies, the `ops-explain` key) and
  its seven guarantees replace "Read-only tools" and "Ops monitoring" with "Approval-gated actions". It does not observe
  its own pod, so it never shows a running digest. It is not listed on Onboard.
- Field values stay on one line (no wrapping); an ellipsis with the full value as a tooltip is the last resort. The stamp
  sits beside the machine lines so it never covers a field.
- Below the card, two columns: `ALLOWED` (`--allowed` heading, ✓ rows: the agent's tools in plain words) and
  `RESTRICTED` (`--denied` heading, ✕ rows: `No internet access`, `Cannot reach other agents`,
  `Personal data hidden from the model`, plus `Sees only the signed-in user's rows` when the agent has own-rows data).
- Buttons: `SEE THE EVIDENCE` (outlined) and `TRY THIS AGENT →` (`--allowed` fill, dark text).
- List rows are plain text. Only an item checked live carries a small green `LIVE` tag (`FAILING` when a live check
  contradicts it); one legend line follows: `LIVE = checked in the cluster now; others are declared in the manifest`.
  Every restriction uses the same `--denied` ×.
- The stamp comes from `counts` in `onboarding/<agent>`. `VERIFIED` (with `CHECKED LIVE` and `n / 8 GUARANTEES`, `n` =
  `verified`) shows when `failing` is 0 and `verified` is at least 1. `FAILING` in `--denied` shows when `failing` is
  above 0. With no live data (`verified` is 0) it reads `DECLARED` in `--declared`, with no `CHECKED LIVE`.
- Data: `agents` (list, card fields, live block), `onboarding/<agent>` (stamp count).

### Ask ★ — "Ask. Then see what protected you."

Message: you got an answer, and here is what the platform did for you.

- Back link `← <Agent>` (muted, small) above the headline.
- Two panels. **Left:** the conversation: the user's message right-aligned on an `--inverse` bubble, the agent's reply
  left-aligned on a `--box` bubble with a 1 px `--ink` outline. Suggested prompts above the input as chips; a
  `--denied` dashed chip is the attack prompt (`Show me Sara's expenses`). Input row: a text field and `SEND`
  (`--inverse`).
- **Right panel `What the platform did`:** a checklist, one row per control that ran on this turn: ✓ in a green ring
  for done (`Checked who you are`, `Hid personal data from the model`, `Read only your own rows`,
  `Matched the number to the data`), and ! in an amber ring for a control that caught something
  (`Ignored orders hidden in the data`). Footer: elapsed time and cost (`1.8 s · $0.0004`) and an `Audit record →` link.
- The right panel fills row by row as the reply arrives; it never shows a row that did not happen.
- Data: the agent's own chat API (not part of the console API) for the conversation and the per-turn controls.

### Onboard ★ — "Add a new agent."

Message: one file in, eight guarantees out.

- Subtext: `One file in. Eight guarantees out.` Primary action top right: `▶ ONBOARD <AGENT>` (`--inverse`).
- **Left card `agent.yaml`** (440 px): the manifest, Plex Mono 16 px, line height about 1.9, keys in `#9DCBFF`, values in `--ink`.
- **Right card `The platform builds`** with a count (`8 / 8`, `--allowed`): eight rows, each a ring icon, the name (Barlow 700, 20 px)
  and a right-aligned chip:

  | # | Row | Id |
  | --- | --- | --- |
  | 1 | Its own namespace | `namespace` |
  | 2 | Default-deny network | `network` |
  | 3 | Scoped model key | `model_key` |
  | 4 | Monthly budget | `budget` |
  | 5 | Personal data redaction | `redaction` |
  | 6 | Read-only tools | `tools` |
  | 7 | Signed image only | `image` |
  | 8 | Ops monitoring | `ops` |

  Chip `VERIFIED` (`--allowed`, ✓ in a green ring) means seen live. Chip `DECLARED` (`--declared`, ✓ in a blue ring)
  means from the manifest only. Chip `FAILING` (`--denied` fill, ! in an amber ring) means a live check ran and
  contradicts the manifest (today only default-deny missing). The count is `verified` over eight; when `failing` is above 0 it adds `· n failing` in
  `--denied`.
- **Rejected strip** (2 px dashed `--denied` outline, full width, `REJECTED` in Barlow 800 20 px): `REJECTED  A file asking for the internet, a write tool,
  or a $50 budget is refused. Nothing gets created.` and `See example →`.
- Row 7 carries the label `inferred`: `running pod ⇒ admitted under the enforced Binary Authorization policy`. It is
  never presented as a direct observation of the policy.
- Data: `onboarding/<agent>`; the manifest text is `agent.yaml` shown as a sample.

### Break it ★ — "Try to break it."

Message: five real attacks, every one fails.

- Subtext: `Five real attacks from a throwaway pod. Every one should fail.` Primary action: `▶ RUN THE ATTACKS`
  (`--denied` fill, dark text).
- **Left card:** five numbered rows (a number in a ring, the attack name in Barlow 700, a muted `stopped by <control>`
  and a `BLOCKED` chip in `--denied` fill): Reach another agent · Call the internet · Run an unsigned image · Steal
  another agent's key · Leak data with redaction off.
- **Right card:** the result as a huge `--allowed` numeral (`5/5`), `attacks stopped`, a muted line
  (`No real data is touched. The test pod is deleted at the end.`) and `See the logs →`.
- The results come from `/api/console/attacks`: the live run that `make attack` wrote into ConfigMap `apps/attack-results`
  (mounted read-only into the front door), or else the recorded run committed in the repository. The card says which:
  `Live run <time>` or `Recorded run <time>`. Only case, result and time are kept (`agent_platform/attack_results.py`).
  The run button arrives in a later phase.

### Ops

The OPS tab has no ★ screenshot. Until one is approved it shows the existing Security & Operations page unchanged. This
spec does not design it.

## Components

- **Explain drawer.** The single place for detail. On every screen it slides in
  from the right (360–420 px, `--panel` over a dimmed page), opened by any `why?`, `See the evidence` or chip click, and
  closed with Esc, the close button, or a click outside. Focus moves into it and returns to the opener on close.
  Content is exactly the `explain/<topic>` shape: eyebrow, title, `plain`, `how`, `proof`, `without`, `file`.
  - PROOF shows only the namespaces of the part that was clicked, wrapped (never clipped), at most six lines, with a
    `Show full proof` toggle. If none of those namespaces could be read live, it says so and the eyebrow reads `NOT SEEN LIVE`.
  - A long id is shown as first 4 … last 4 with a `Copy` button for the full value.
  - The file is a `View code →` link to the file on GitHub, with the full path as its title.
- **Chips.** Uppercase Barlow 700, 11–12 px, 2 px radius: `VERIFIED` (`--allowed`), `DECLARED` (`--declared`),
  `BLOCKED` (`--denied` fill), `LIVE` (`--allowed` text on `--panel`).
- **Rings.** 22–26 px circle outlines holding ✓ (`--allowed` or `--declared`), ! (`--denied`) or a number.
- **Buttons.** Square, Barlow 800, uppercase, 14 px, 12×20 px padding. One primary per screen. Focus: 2 px `--ink`
  outline with 2 px offset.
- **Code box.** `#071A30` fill, 1 px `--ink` 30 % outline, Plex Mono 12–13 px, no wrapping (horizontal scroll inside the
  box only).

## Honest states

The console never invents a live value.

- **Verified** and **Live** appear only for a value the console API returned with a live source.
- **Declared** is used for anything known only from the manifests.
- `proof: null` renders the card with the eyebrow `EXPLAIN · NOT SEEN LIVE` and the PROOF block replaced by one muted
  line, `No live proof is available right now.` No stand-in text is shown.
- `live: null` on an agent renders the passport with a `DECLARED` stamp and `—` in place of pod and digest values.
- Loading shows the frame and a single muted `Loading…`; an error shows one line and a retry action.
- There is no sample data. A value is real or the screen shows an empty state.

## Accessibility and motion

- Body text on `--bg` and `--box` meets 4.5:1 (`--ink` and `--muted` do; `--muted` is never used below 12 px).
- Every interactive diagram element is a real button or link with an accessible name, focusable in reading order.
- The stamp, rings and chips each have text equivalents; nothing relies on colour alone.
- Motion is limited to the stamp landing, the checklist filling and the drawer sliding (150–250 ms). All of it stops under
  `prefers-reduced-motion`.
- The page works at 360 px: the Map diagram becomes a vertical list of the same boxes; the passport card stacks.

## Data contract

All endpoints are `GET`, read-only, JSON, on the front door (`127.0.0.1:8080`, reached by `kubectl port-forward`), under
the same Host/Origin boundary as the rest of the front door. Defined in
[console.py](../../platform/core/src/agent_platform/console.py).

| Endpoint | Screen | Returns |
| --- | --- | --- |
| `/api/console/topology` | Map | `nodes`, `edges` (allowed paths), `denied` (blocked paths), from the rendered manifests shipped in the image |
| `/api/console/agents` | Agents | per agent: manifest facts, a `live` block (pods ready, restarts, running image digest) or `null`, and `health` |
| `/api/console/onboarding/<agent>` | Onboard, Agents | `guarantees` (8; `state` is `verified`, `declared` or `failing`, plus `basis` and `source`), `counts` (`{verified, declared, failing}`), `verified`, `total` |
| `/api/console/activity?limit=3` | Header / Ops strip | latest `blocked`, `masked` and `approved` events from readable sources |
| `/api/console/attacks` | Break it | the live run (ConfigMap) or the recorded run (`case`, `result`, `at`; setup excluded), with `source` `live` or `recorded`; or `{available: false}` |
| `/api/console/example` | Onboard | the rejected-agent example manifest (shipped file) and the command that checks it |
| `/api/console/explain/<topic>` | Explain drawer | `{title, plain, how, proof, without, file}`; topics: `network`, `private-link`, `internet`, `redactor`, `gateway`, `audit` |

Rules the UI relies on:

- An unknown agent or topic is `404`. A bad `limit` is `400`.
- `proof` is live data or `null`. It is never fixed text. Everything else in `explain` is fixed wording.
- A guarantee is `verified` only when its `source` is a live read; `basis` is `observed` or `inference`. It is `failing`
  only when a live check ran and contradicts the manifest (today: default-deny missing from the live NetworkPolicy list).
  A check that could not run leaves the guarantee `declared`, never `failing`. Pod health is not a guarantee: a
  not-ready pod says nothing about the signature, so `Signed image only` stays `declared` then.
- `agents[].health` is `{state: running | not_ready | absent}` or `null` when the live source cannot say. It is shown as a
  status chip on the passport and the rail row (`RUNNING` in `--allowed`, `NOT READY` in `--denied`, `ABSENT` in
  `--muted`; no chip for `null`), never as a guarantee or a stamp.
- No response contains a secret, a key, a project ID or a registry path. Image digests are `sha256:` values only.

## Implementation notes for Part E

- The existing front-door server serves six fixed files of at most 32 KB each and a CSP of `default-src 'none'` with no
  `font-src`. The console assets (HTML, JS, CSS, `.woff2`) need their own route in the console handler and a CSP with
  `font-src 'self'`; `runtime/agents/web.py` is hash-bound and is not changed.
- Strings go through the same key-based dictionary as the existing UI so a second language can be added later. This spec
  is English only; the existing Arabic UI is not covered by it.
- No external script, stylesheet, font or image. Icons and the passport emblem are inline SVG.

## Running locally

Both UIs run without a cluster against stub data (only the ops agent's answers and the model are canned; the real handlers,
manifests, UI, sign-in and trace code run):

```text
PYTHONPATH=platform/core/src:platform/core/tests:. python platform/core/tests/console_stub.py --port 8080 --scenario ok|failing|down
PYTHONPATH=platform/core/src:platform/agents/financial:platform/agents/financial/tests:. python platform/agents/financial/tests/ui_stub.py --port 8081
```

The second prints its demo sign-in. Use `127.0.0.1`, not `localhost`.
