# The Financial Agent's own image (platform/agents/financial/agent.yaml: image agent-financial). Built, scanned
# (Trivy HIGH/CRITICAL fail-closed), SBOM'd, keyless-signed and KMS-attested by the same CI pipeline as the platform
# images (.github/workflows/agent-platform-images.yml). Contents: the agent's code, the platform client SDK
# (redaction client, audit) and hash-locked dependencies. Nonroot, no shell, read-only root filesystem at runtime.
FROM python:3.12.15-slim-trixie@sha256:29113dcae7aad06daa8e95260fa09f27d62be33b9687ea3774f771d601a02256 AS builder
COPY requirements-agent-composition.txt requirements-financial-agent.txt /tmp/
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
      -r /tmp/requirements-agent-composition.txt -r /tmp/requirements-financial-agent.txt \
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
COPY --chown=65532:65532 platform/core/src/agent_platform/__init__.py platform/core/src/agent_platform/audit.py platform/core/src/agent_platform/identifiers.py platform/core/src/agent_platform/redaction.py platform/core/src/agent_platform/release_version.py platform/core/src/agent_platform/masking_scope.py platform/core/src/agent_platform/request_context.py platform/core/src/agent_platform/boundary_http.py platform/core/src/agent_platform/data_capability.py /app/platform/src/agent_platform/
COPY --chown=65532:65532 platform/agents/financial/finance_agent/ /app/finance_agent/
ENTRYPOINT ["/usr/local/bin/python3.12", "-m", "finance_agent.worker"]
