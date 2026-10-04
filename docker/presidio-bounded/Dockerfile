# Local qualification candidate only; never published or deployment-selected.
FROM python:3.12.15-slim-trixie@sha256:29113dcae7aad06daa8e95260fa09f27d62be33b9687ea3774f771d601a02256 AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY requirements-presidio-runtime.txt /build/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --require-hashes --only-binary=:all: -r /build/requirements.txt \
    && /opt/venv/bin/pip check

FROM python:3.12.15-slim-trixie@sha256:29113dcae7aad06daa8e95260fa09f27d62be33b9687ea3774f771d601a02256
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
COPY --from=dependencies /opt/venv /opt/venv
COPY --chown=65532:65532 docker/presidio-bounded/server.py /app/server.py
USER 65532:65532
WORKDIR /app
ENTRYPOINT ["/opt/venv/bin/python", "-B", "/app/server.py"]
