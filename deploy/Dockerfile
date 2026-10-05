# Build only from scripts/prepare_container.py output (hashed installed wheels).
FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3 AS install
COPY wheels /wheels
COPY requirements-analysis.lock /requirements-analysis.lock
COPY manifest.json /manifest.json
RUN python -c 'import hashlib,json,pathlib; m=json.load(open("/manifest.json")); assert hashlib.sha256(pathlib.Path("/requirements-analysis.lock").read_bytes()).hexdigest()==m["lock_sha256"]; assert all(hashlib.sha256((pathlib.Path("/wheels")/n).read_bytes()).hexdigest()==h for n,h in m["wheels"].items()); assert set(p.name for p in pathlib.Path("/wheels").iterdir())==set(m["wheels"])' \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-index --find-links=/wheels --require-hashes --only-binary=:all: -r /requirements-analysis.lock \
    && /opt/venv/bin/pip install --no-index --no-deps /wheels/plat*.whl \
    && /opt/venv/bin/pip check
FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.title="Platworks reference library and scenario MCP" \
      org.opencontainers.image.version="0.1.4" \
      org.opencontainers.image.source="https://github.com/paintbrushv/platworks" \
      org.opencontainers.image.revision=$SOURCE_REVISION \
      org.opencontainers.image.licenses="Apache-2.0"
COPY --from=install /opt/venv /opt/venv
COPY --from=install /manifest.json /opt/platworks-build.json
ENV PATH="/opt/venv/bin:$PATH" TMPDIR=/tmp PYTHONDONTWRITEBYTECODE=1
WORKDIR /tmp
USER 65532:65532
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -I -c 'import os,urllib.request; h=os.environ.get("PLATWORKS_ALLOWED_HOSTS","127.0.0.1:8000").split(",")[0]; r=urllib.request.Request("http://127.0.0.1:8000/healthz",headers={"Host":h}); urllib.request.urlopen(r,timeout=2).close()'
ENTRYPOINT ["/opt/venv/bin/python", "-I", "-B", "-m", "platworks.mcp_http"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
