# Supply-chain policy

The standalone CI validates source scope, schemas, runtime controls, YAML, and Git history secrets. It does not build, publish, sign, or deploy images.

The original infrastructure work established a design for immutable image digests, dependency and image vulnerability scanning, CycloneDX SBOM generation, signature verification, and evidence-bound promotion. A production pipeline should pin tools and actions, retain complete scanner outputs and SBOMs, verify provenance before promotion, and reject unsigned or mutable image references. Exceptions must identify an exact image digest, package, version, advisory, owner, justification, and expiry. Known exploited vulnerabilities and fixable critical findings remain blocking.

The public image digests in `kubernetes/` are historical examples of immutable references. A target deployment must confirm current upstream provenance, platform compatibility, support status, vulnerabilities, and runtime behavior. A successful source test or Kustomize render is not an image release decision.
