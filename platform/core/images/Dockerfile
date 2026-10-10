# Agent platform images: `app` (bilingual UI + Financial Agent + bootstrap/fault programs) and `ops` (Security &
# Operations Agent). Same digest-pinned bases and the same hash-locked dependency set as the qualified
# docker/agent-composition image (no new dependency); built, scanned, SBOM'd, keyless-signed and KMS-attested by
# .github/workflows/agent-platform-images.yml. Nonroot, no shell, read-only root filesystem at runtime.
FROM python:3.12.15-slim-trixie@sha256:29113dcae7aad06daa8e95260fa09f27d62be33b9687ea3774f771d601a02256 AS builder
COPY requirements-litellm-candidate.txt requirements-agent-composition.txt /tmp/
RUN mkdir -p /out/usr/local/bin /out/usr/local/lib \
    && cp /usr/local/bin/python3.12 /out/usr/local/bin/ \
    && cp /usr/local/lib/libpython3.12.so* /out/usr/local/lib/ \
    && cp -a /usr/local/lib/python3.12 /out/usr/local/lib/ \
    && rm -rf /out/usr/local/lib/python3.12/site-packages \
      /out/usr/local/lib/python3.12/ensurepip /out/usr/local/lib/python3.12/test \
      /out/usr/local/lib/python3.12/idlelib /out/usr/local/lib/python3.12/tkinter \
      /out/usr/local/lib/python3.12/turtledemo /out/usr/local/lib/python3.12/venv \
      /out/usr/local/lib/python3.12/pydoc_data \
    && python -m pip install --require-hashes --no-cache-dir \
      --target=/out/usr/local/lib/python3.12/site-packages \
      -r /tmp/requirements-litellm-candidate.txt -r /tmp/requirements-agent-composition.txt \
    && find /out -type d -name __pycache__ -prune -exec rm -rf {} +

FROM gcr.io/distroless/base-debian13:nonroot@sha256:a0d70d6a97cd697d9362bc2aae4a6560dd65817e365d0043b07325a97975dc91 AS runtime
COPY --from=builder /out/usr/local /usr/local
COPY --from=builder /lib/x86_64-linux-gnu/libgcc_s.so.1 /lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libstdc++.so.6 /lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libffi.so.8 /lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libsqlite3.so.0 /lib/x86_64-linux-gnu/
ENV LD_LIBRARY_PATH=/usr/local/lib \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    PYTHONPATH=/app/platform/src:/app \
    HOME=/tmp
USER 65532:65532
WORKDIR /app
COPY --chown=65532:65532 runtime/ /app/runtime/
COPY --chown=65532:65532 contracts/ /app/contracts/
COPY --chown=65532:65532 platform/core/src/ /app/platform/src/

FROM runtime AS app
COPY --chown=65532:65532 demo/ /app/demo/
# Platform dashboard v1 (agent timeline, pending approvals, policy denials) over the retained local UI files;
# demo/ui stays byte-identical so earlier qualification records remain valid.
COPY --chown=65532:65532 platform/core/ui/ /app/demo/ui/
COPY --chown=65532:65532 evaluation/agent-composition/ /app/evaluation/agent-composition/
ENTRYPOINT ["/usr/local/bin/python3.12", "-m", "agent_platform.app"]

FROM runtime AS ops
ENTRYPOINT ["/usr/local/bin/python3.12", "-m", "agent_platform.ops.server"]
