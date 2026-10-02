# Vulnerability policy inputs

`empty-exceptions.json` is the active default: it approves nothing. The [evaluator](../scripts/evaluate-container-vulnerability-policy.py) consumes a complete Trivy JSON report, exact digest-pinned subject, current CISA KEV feed, and an exception register. A future approval must be reviewed and bound to the exact subject and finding; never import the source project's VEX or exception records.

Use synthetic fixtures for repository tests. A real promotion decision requires a fresh scanner report, independently verified image identity, current KEV data, SBOM, provenance, approval evidence and signature verification. This directory by itself grants no promotion.
