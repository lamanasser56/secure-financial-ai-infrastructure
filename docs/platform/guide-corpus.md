# Guide documentation corpus

`platform/agents/platform-guide/current-docs.json` is the reviewed file selection for the current platform Guide. Adding a Markdown file does not add it to model knowledge. Historical ADRs, campaign bundles, evidence and private handoffs are not a fallback when a current query has no answer. The builder reads selected files only and does not follow their links or fetch a website.

The index producer validates the manifest, refuses missing/outside/symlinked/empty/oversized inputs, sanitizes content and creates bounded heading-aware chunks. Original document hashes, manifest hash, corpus/review identity and declared source commit are retained. Chunk IDs bind path, heading and sanitized text. The runtime accepts the current closed format and refuses obsolete or modified indexes rather than repairing them.

The Guide image build supplies its explicit source commit from the CI-validated checkout. The production CLI requires that commit; test builds can be explicitly unbound. **These are build metadata and content hashes, not cryptographic source proof.** Exact image subject, signer/attestor and independently bound source provenance must be verified separately for a release.

Updating a selected document, corpus selection or index producer requires rebuilding its consuming Guide image. The final source freeze and image-input graph govern the release; a modified document on disk does not update an existing running image. Do not substitute a historical index or a mounted source patch for that build.

The Arabic platform overview provides current Arabic retrieval material. Index/search tests use the real reviewed corpus as well as explicitly synthetic unit fixtures. Synthetic model transports exercise the current HTTP composition without external LLM calls. Source presentation, answer admission and requested-language behaviour are separate application responsibilities; a hit count or figure check alone is not proof of all answer claims.
