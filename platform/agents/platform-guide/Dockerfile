# The Platform Guide's own image (platform/agents/platform-guide/agent.yaml: image platform-guide). Built, scanned
# (Trivy HIGH/CRITICAL fail-closed, KEV gate), SBOM'd, keyless-signed and KMS-attested by the same CI pipeline as the
# other platform images (.github/workflows/agent-platform-images.yml). Contents: the agent's code and a docs index
# built from docs/ at image build time. No npm dependencies. Nonroot, no shell, read-only root filesystem at runtime.
FROM node:24-trixie-slim@sha256:7f486cabe892bff8fef04c0f7da8dba84a560be3e4e2740b7a86afc57ebec315 AS builder
WORKDIR /build
COPY docs/ ./docs/
COPY platform/agents/platform-guide/tools/ ./tools/
RUN node tools/build-index.js docs docs-index.json

FROM gcr.io/distroless/nodejs24-debian13:nonroot@sha256:59c479c9b8c123e66047315c968aa2d35e31ae5149c856e4110a79c8b3563f0b AS runtime
WORKDIR /app
COPY --chown=65532:65532 platform/agents/platform-guide/package.json ./
COPY --chown=65532:65532 platform/agents/platform-guide/src/ ./src/
COPY --chown=65532:65532 platform/agents/platform-guide/public/ ./public/
COPY --from=builder --chown=65532:65532 /build/docs-index.json ./docs-index.json
USER 65532:65532
ENV NODE_ENV=production
ENTRYPOINT ["/nodejs/bin/node", "src/server.js"]
