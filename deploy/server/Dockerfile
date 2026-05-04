# Multi-stage build for hl_helper FastAPI server.
# Produces a minimal image with non-root user and venv.
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
COPY server ./server
COPY agent ./agent
RUN pip install --no-cache-dir --disable-pip-version-check . \
    && pip install --no-cache-dir httpx

FROM python:3.12-slim AS runtime
RUN groupadd -r hl && useradd -r -g hl -u 10001 hl \
    && mkdir -p /app/data \
    && chown -R hl:hl /app
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --chown=hl:hl server ./server
USER hl
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx,sys; r=httpx.get('http://localhost:8000/v1/observability/health', timeout=5); sys.exit(0 if r.status_code==200 else 1)" || exit 1
ENTRYPOINT ["uvicorn", "server.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
