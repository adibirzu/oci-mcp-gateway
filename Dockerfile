# syntax=docker/dockerfile:1.7

# Reproducible linux/amd64 gateway image. The lock file pins the gateway engine
# to an exact Git revision and resolves every Python dependency.
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir "uv==0.11.21"

WORKDIR /build

COPY uv.lock pyproject.toml README.md ./
COPY src/ src/

RUN uv sync --frozen --no-dev --extra otel --no-editable \
    && /opt/venv/bin/python -c \
      "import mcp_server_oci, oci_mcp_gateway; print('gateway runtime imports verified')"

FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS runtime

ENV PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_GATEWAY_CONFIG=/app/config/gateway.json \
    MCP_GATEWAY_HOST=0.0.0.0 \
    MCP_GATEWAY_PORT=9000

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 gateway \
    && useradd \
      --uid 10001 \
      --gid 10001 \
      --no-create-home \
      --home-dir /nonexistent \
      --shell /usr/sbin/nologin \
      gateway

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=10001:10001 config/gateway.json config/gateway.json

USER 10001:10001

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail --silent --show-error --output /dev/null \
      http://127.0.0.1:9000/health || exit 1

ENTRYPOINT ["python", "-m", "oci_mcp_gateway"]
