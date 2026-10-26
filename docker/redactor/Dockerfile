# Persistent SDP service; provider adapter, transport and policy are image-owned.
FROM python:3.12.15-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS builder
COPY requirements-google-sdp-runtime.txt /tmp/
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
      -r /tmp/requirements-google-sdp-runtime.txt \
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
COPY --chown=65532:65532 runtime/phase3/ /app/runtime/phase3/
COPY --chown=65532:65532 platform/core/src/agent_platform/__init__.py /app/platform/src/agent_platform/
COPY --chown=65532:65532 platform/core/src/agent_platform/programs/__init__.py platform/core/src/agent_platform/programs/phone_guard.py platform/core/src/agent_platform/programs/redactor_server.py /app/platform/src/agent_platform/programs/

COPY --chown=65532:65532 evaluation/google-sdp/deployment.json /app/evaluation/google-sdp/
COPY --chown=65532:65532 evaluation/google-sdp-context/policy.json /app/evaluation/google-sdp-context/
ENTRYPOINT ["/usr/local/bin/python3.12", "-m", "agent_platform.programs.redactor_server"]
