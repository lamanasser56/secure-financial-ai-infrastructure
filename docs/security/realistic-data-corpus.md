# Synthetic masking and agent test corpus

`platform/core/tests/corpus/make_corpus.py` deterministically creates the committed `saudi_bilingual_corpus.json` used by current offline tests. Review the generator and current output for the actual cases/counts rather than borrowing a previous report's totals. The corpus includes Arabic/English shapes, supported-pattern positives/negatives, instruction-like text and grounding examples.

Records are constructed for testing, not copied from real users. A structurally valid invented number is not proof of an officially reserved or unassigned identifier. A prior NXDOMAIN check is not a permanent reservation of a domain. Never contact a generated address/number, import real account records or treat plausible formatting as provenance.

Names/passport examples document the unsupported boundary: **person names and passport numbers are not masked**. Other positives test the supported shape/context rules; they do not establish every possible representation. Compare against the actual runtime category set and [current scope](masking-scope.md).

The dated [realistic-data review](realistic-data-review-2026-10.md) records its source, inputs and results. It is historical evidence, not a current-image pass. Any live corpus use belongs in the approved final qualification scope with synthetic data, bounded resource controls and the exact selected images. A test transport or local double is not a real provider result.
