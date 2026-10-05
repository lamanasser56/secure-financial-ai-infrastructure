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
# The generated client/engine are separately hashed build subjects prepared with
# the locked official schema. Build admission verifies their entire inventory.
COPY --chown=65532:65532 .qualified/prisma/ /out/usr/local/lib/python3.12/site-packages/prisma/
FROM gcr.io/distroless/base-debian13:nonroot@sha256:a0d70d6a97cd697d9362bc2aae4a6560dd65817e365d0043b07325a97975dc91 AS runtime
COPY --from=builder /out/usr/local /usr/local
COPY --from=builder /lib/x86_64-linux-gnu/libgcc_s.so.1 /lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libstdc++.so.6 /lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libffi.so.8 /lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libsqlite3.so.0 /lib/x86_64-linux-gnu/
COPY .qualified/query-engine /usr/local/lib/prisma/query-engine
ENV LD_LIBRARY_PATH=/usr/local/lib \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    PRISMA_QUERY_ENGINE_BINARY=/usr/local/lib/prisma/query-engine \
    LITELLM_LOCAL_MODEL_COST_MAP=True \
    LITELLM_TELEMETRY=False \
    DISABLE_ADMIN_UI=True \
    DISABLE_SCHEMA_UPDATE=true \
    HOME=/tmp
USER 65532:65532
WORKDIR /app
FROM runtime AS gateway
COPY --chown=65532:65532 scripts/local-agent-proxy.py /app/proxy.py
ENTRYPOINT ["/usr/local/bin/python3.12", "/app/proxy.py"]
FROM runtime AS application
COPY --chown=65532:65532 runtime/ /app/runtime/
COPY --chown=65532:65532 contracts/ /app/contracts/
COPY --chown=65532:65532 demo/ /app/demo/
COPY --chown=65532:65532 scripts/serve-integrated-agents.py /app/scripts/serve-integrated-agents.py
COPY --chown=65532:65532 scripts/run-local-operations.py scripts/inspect-operations-active-path.py /app/scripts/
COPY --chown=65532:65532 scripts/evaluate-container-vulnerability-policy.py /app/scripts/
COPY --chown=65532:65532 scripts/rehearse-operations-reasoning.py /app/scripts/
COPY --chown=65532:65532 evaluation/operations /app/evaluation/operations
ENTRYPOINT ["/usr/local/bin/python3.12", "/app/scripts/serve-integrated-agents.py"]
