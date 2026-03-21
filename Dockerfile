# Gateway image — thin wrapper around mcp-server-oci gateway module
# Build on x86_64 VM (never locally on ARM).
# Requires mcp-server-oci source at /tmp/mcp/mcp-oci/ on the build VM.
#
# Build context: /tmp/mcp/oci-mcp-gateway/
# Pre-step: copy mcp-oci source into build context:
#   cp -r /tmp/mcp/mcp-oci /tmp/mcp/oci-mcp-gateway/_mcp-oci

# ── Stage 1: Builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /build

# Install mcp-server-oci (local source) first
COPY _mcp-oci/pyproject.toml _mcp-oci/README.md _mcp-oci/
COPY _mcp-oci/src/ _mcp-oci/src/
RUN uv pip install --system --no-cache "./_mcp-oci"

# Install this gateway wrapper + OTEL deps
COPY pyproject.toml .
COPY src/ src/
RUN uv pip install --system --no-cache ".[otel]"

# ── Stage 2: Runtime ──────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN groupadd -g 1000 mcp && useradd -u 1000 -g mcp -s /bin/sh mcp

# Minimal runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app
COPY src/ src/
COPY config/gateway.json config/gateway.json

RUN chown -R mcp:mcp /app

USER mcp

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_GATEWAY_CONFIG=/app/config/gateway.json \
    MCP_GATEWAY_HOST=0.0.0.0 \
    MCP_GATEWAY_PORT=9000

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fs -o /dev/null -w '' http://127.0.0.1:9000/mcp || exit 1

ENTRYPOINT ["python", "-m", "oci_mcp_gateway"]
