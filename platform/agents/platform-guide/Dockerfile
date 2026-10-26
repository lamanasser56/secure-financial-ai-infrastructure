# The Platform Guide's own image (platform/agents/platform-guide/agent.yaml: image platform-guide). Built, scanned
# (Trivy HIGH/CRITICAL fail-closed, KEV gate), SBOM'd, keyless-signed and KMS-attested by the same CI pipeline as the
# other platform images (.github/workflows/agent-platform-images.yml). Contents: the agent's code and a docs index
# built from docs/ at image build time. No npm dependencies. Nonroot, no shell, read-only root filesystem at runtime.
FROM node:24-trixie-slim@sha256:43b9ba1142b8dcf33fa8f922ca1be85714adc444e0586c7cf7726daaeabc1bea AS builder
WORKDIR /build
COPY docs/ ./docs/
COPY platform/agents/platform-guide/tools/ ./tools/
RUN node tools/build-index.js docs docs-index.json

FROM gcr.io/distroless/nodejs24-debian13:nonroot@sha256:cb606325b7ec4af55462cb0b424a53b452a5b4a894ffe841fcf1048d216fb9f8 AS runtime
WORKDIR /app/platform/agents/platform-guide
COPY --chown=65532:65532 platform/agents/platform-guide/package.json ./
COPY --chown=65532:65532 platform/agents/platform-guide/src/ ./src/
COPY --chown=65532:65532 platform/agents/platform-guide/public/ ./public/
COPY --chown=65532:65532 platform/core/ui/core.js platform/core/ui/style.css platform/core/ui/shared-assets.json /app/platform/core/ui/
COPY --chown=65532:65532 platform/core/ui/typeface/ /app/platform/core/ui/typeface/
COPY --from=builder --chown=65532:65532 /build/docs-index.json ./docs-index.json
USER 65532:65532
ENV NODE_ENV=production
ENTRYPOINT ["/nodejs/bin/node", "src/server.js"]
