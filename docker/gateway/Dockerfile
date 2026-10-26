# Image-owned LiteLLM service, generated Prisma client and supported ASGI/config interfaces.
FROM node:24-trixie-slim@sha256:43b9ba1142b8dcf33fa8f922ca1be85714adc444e0586c7cf7726daaeabc1bea AS node-tool
FROM python:3.12.15-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS builder
COPY --from=node-tool /usr/local/bin/node /opt/node/bin/node
COPY --from=node-tool /usr/local/lib/node_modules/npm /opt/node/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /opt/node/bin/npm
ENV PATH=/opt/node/bin:$PATH PRISMA_USE_GLOBAL_NODE=true
COPY requirements-gateway.txt /tmp/
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
      -r /tmp/requirements-gateway.txt \
    && find /out -type d -name __pycache__ -prune -exec rm -rf {} +

RUN PATH=/out/usr/local/lib/python3.12/site-packages/bin:$PATH \
      PYTHONPATH=/out/usr/local/lib/python3.12/site-packages \
      PRISMA_BINARY_PLATFORM=debian-openssl-3.0.x python -m prisma generate \
      --schema=/out/usr/local/lib/python3.12/site-packages/litellm/proxy/schema.prisma \
    && mkdir -p /out/prisma \
    && find /root/.cache/prisma-python -type f -name 'query-engine-debian-openssl-3.0.x' -exec cp {} /out/prisma/query-engine \; \
    && test -x /out/prisma/query-engine
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
COPY --chown=65532:65532 platform/core/src/agent_platform/__init__.py /app/platform/src/agent_platform/
COPY --chown=65532:65532 platform/core/src/agent_platform/programs/__init__.py platform/core/src/agent_platform/programs/gateway_hooks.py /app/platform/src/agent_platform/programs/

COPY --from=builder /out/prisma/ /app/prisma/
ENV CONFIG_FILE_PATH=/config/litellm.yaml \
    PRISMA_BINARY_PLATFORM=debian-openssl-3.0.x \
    PRISMA_QUERY_ENGINE_BINARY=/app/prisma/query-engine \
    DISABLE_SCHEMA_UPDATE=true \
    LITELLM_LOCAL_MODEL_COST_MAP=true \
    LITELLM_DISABLE_LATEST_RELEASE_CHECK=true \
    DO_NOT_TRACK=true
ENTRYPOINT ["/usr/local/bin/python3.12", "-m", "uvicorn", "litellm.proxy.proxy_server:app", "--host", "0.0.0.0", "--port", "4001", "--workers", "1", "--no-access-log"]
