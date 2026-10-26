FROM python:3.12.15-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS builder
COPY requirements-google-sdp-runtime.txt /tmp/requirements.txt
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
      --target=/out/usr/local/lib/python3.12/site-packages -r /tmp/requirements.txt \
    && find /out -type d \( -name __pycache__ -o -name tests -o -name test \) -prune -exec rm -rf {} +
FROM gcr.io/distroless/base-debian13:nonroot@sha256:f9518b74815721f537a7458cc693b4406208c04fce23bbffab511516117f34fd
COPY --from=builder /out/usr/local /usr/local
COPY --from=builder /lib/x86_64-linux-gnu/libgcc_s.so.1 /lib/x86_64-linux-gnu/
COPY --from=builder /lib/x86_64-linux-gnu/libstdc++.so.6 /lib/x86_64-linux-gnu/
WORKDIR /app
COPY --chown=65532:65532 --chmod=0555 scripts/evaluate-sdp-context-policy.py /app/scripts/
COPY --chown=65532:65532 --chmod=0555 runtime/phase3/__init__.py runtime/phase3/google_sdp_adapter.py runtime/phase3/sdp_context_policy.py runtime/phase3/trusted_runtime.py /app/runtime/phase3/
COPY --chown=65532:65532 --chmod=0555 evaluation/google-sdp/deployment.json /app/evaluation/google-sdp/
COPY --chown=65532:65532 --chmod=0555 evaluation/google-sdp-context/policy.json evaluation/google-sdp-context/corpus.json evaluation/google-sdp-context/corpus.schema.json evaluation/google-sdp-context/result.schema.json /app/evaluation/google-sdp-context/
ENV LD_LIBRARY_PATH=/usr/local/lib PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/python3.12", "/app/scripts/evaluate-sdp-context-policy.py"]
CMD []
