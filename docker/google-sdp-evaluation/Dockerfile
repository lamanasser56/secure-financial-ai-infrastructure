# syntax=docker/dockerfile:1
FROM python:3.12.15-slim-trixie@sha256:29113dcae7aad06daa8e95260fa09f27d62be33b9687ea3774f771d601a02256 AS builder

COPY requirements-google-sdp-runtime.txt /tmp/requirements.txt
RUN mkdir -p /out/usr/local/bin /out/usr/local/lib \
    && cp /usr/local/bin/python3.12 /out/usr/local/bin/ \
    && cp /usr/local/lib/libpython3.12.so* /out/usr/local/lib/ \
    && cp -a /usr/local/lib/python3.12 /out/usr/local/lib/ \
    && rm -rf /out/usr/local/lib/python3.12/site-packages \
      /out/usr/local/lib/python3.12/ensurepip \
      /out/usr/local/lib/python3.12/test \
      /out/usr/local/lib/python3.12/idlelib \
      /out/usr/local/lib/python3.12/tkinter \
      /out/usr/local/lib/python3.12/turtledemo \
      /out/usr/local/lib/python3.12/venv \
      /out/usr/local/lib/python3.12/pydoc_data \
    && python -m pip install --require-hashes --no-cache-dir \
      --target=/out/usr/local/lib/python3.12/site-packages \
      -r /tmp/requirements.txt \
    && find /out -type d \( -name __pycache__ -o -name tests -o -name test \) \
      -prune -exec rm -rf {} +

FROM gcr.io/distroless/base-debian13:nonroot@sha256:a0d70d6a97cd697d9362bc2aae4a6560dd65817e365d0043b07325a97975dc91

COPY --from=builder /out/usr/local /usr/local
# CPython's native dependencies are copied from the same Debian 13 builder.
COPY --from=builder /lib/x86_64-linux-gnu/libgcc_s.so.1 /lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libstdc++.so.6 /lib/x86_64-linux-gnu/

WORKDIR /app
COPY scripts/evaluate-google-sdp.py /app/scripts/
COPY runtime/phase3/__init__.py runtime/phase3/google_sdp_adapter.py runtime/phase3/trusted_runtime.py /app/runtime/phase3/
COPY evaluation/google-sdp/corpus.json evaluation/google-sdp/corpus.schema.json evaluation/google-sdp/result.schema.json /app/evaluation/google-sdp/

ENV LD_LIBRARY_PATH=/usr/local/lib \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/python3.12", "/app/scripts/evaluate-google-sdp.py"]
CMD []
