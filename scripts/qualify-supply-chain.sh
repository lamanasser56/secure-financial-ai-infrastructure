#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# A public digest-pinned image qualifies scanner plumbing only. It is not a
# release subject for the portfolio's Presidio or LiteLLM deployments.
qualification_image='gcr.io/distroless/static-debian12@sha256:f5b485ea962d9bd1186b2f6b3a061191539b905b82ec395de78cbfae51f20e35'
bash scripts/scan-dependencies.sh
bash scripts/scan-image.sh "$qualification_image"
bash scripts/generate-sbom.sh "$qualification_image"
bash scripts/qualify-signatures.sh
