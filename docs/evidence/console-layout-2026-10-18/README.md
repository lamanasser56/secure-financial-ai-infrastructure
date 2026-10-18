# Console layout at 1440 × 900 (2026-10-18)

Screenshots of every console page and the Financial Agent's Ask page at 1440 × 900 (the recording viewport), before and
after the full-width layout change. Taken with headless Chromium from clean checkouts of `main` (1f91e6d) and the change,
each running the repository's local stubs (`platform/core/tests/console_stub.py --scenario ok` and
`platform/agents/financial/tests/ui_stub.py`). Stub data only, with no cluster and no cloud project. The Break it page shows the
recorded run committed in `docs/evidence/attack-suite.json`.

Measured on every page after the change: the document is 1440 × 900 (no horizontal or vertical scroll), no element extends
past the right edge, no text is clipped, and every label in the Map drawing fits inside its box. At 360 px every console page
is 360 px wide. Under `prefers-reduced-motion` the drawing has no moving packets and the × marks do not pulse.

The `after/` set is from bde7aa8. `after/7-map-explain.png` is Map + Explain: Explain opened from the keyboard on a wall chip
appears in the right column (420 px, same top and height as the drawing: both 671 px at y = 176) while the drawing stays
914 px wide and undimmed. Esc brings the aside back and returns focus to the chip. The proof shown is the stub's live
NetworkPolicy answer.
