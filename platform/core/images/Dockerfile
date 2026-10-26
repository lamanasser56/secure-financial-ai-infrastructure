# Console/bootstrap and Ops use a minimal, hash-locked platform dependency set.
# Provider SDKs, LiteLLM and Prisma belong only to their own service images.
FROM python:3.12.15-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS builder
COPY requirements-platform.txt /tmp/
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
      -r /tmp/requirements-platform.txt \
    && find /out -type d -name __pycache__ -prune -exec rm -rf {} +

FROM gcr.io/distroless/base-debian13:nonroot@sha256:f9518b74815721f537a7458cc693b4406208c04fce23bbffab511516117f34fd AS runtime
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
COPY --chown=65532:65532 platform/core/database/ /app/platform/database/
COPY --chown=65532:65532 demo/ /app/demo/
COPY --chown=65532:65532 evaluation/agent-composition/ /app/evaluation/agent-composition/
# Console data API (/api/console/*): the rendered manifests and the agent manifests, read-only, next to the code.
COPY --chown=65532:65532 platform/core/kubernetes/ /app/platform/kubernetes/
COPY --chown=65532:65532 platform/agents/ /app/platform/agents/
COPY --chown=65532:65532 platform/clouds/gke/kubernetes/ /app/platform/gke/
# Console assets and the rejected onboarding example. Attack results come only from the optional runtime mount.
COPY --chown=65532:65532 platform/core/ui/ /app/platform/ui/
COPY --chown=65532:65532 docs/examples/rejected-agent/agent.yaml /app/platform/examples/rejected-agent/agent.yaml
ENTRYPOINT ["/usr/local/bin/python3.12", "-m", "agent_platform.app"]

FROM runtime AS ops
ENTRYPOINT ["/usr/local/bin/python3.12", "-m", "agent_platform.ops.server"]
