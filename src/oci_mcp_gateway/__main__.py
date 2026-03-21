"""OCI MCP Gateway entry point.

Thin wrapper around mcp-server-oci gateway module. Adds OKE-specific
health endpoints and optional OTEL observability before delegating
to the production-grade gateway infrastructure.
"""

from __future__ import annotations

import os
import sys

import structlog

log = structlog.get_logger(__name__)


def main() -> None:
    """Load config, optionally init OTEL, then start the gateway."""
    # Init observability before anything else (if APM domain configured)
    apm_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if apm_endpoint:
        try:
            from oci_mcp_gateway.observability import init_otel

            init_otel()
            log.info("otel_initialized", endpoint=apm_endpoint)
        except ImportError:
            log.warning("otel_packages_not_installed", hint="pip install oci-mcp-gateway[otel]")

    # Import gateway module (mcp-server-oci dependency)
    try:
        from mcp_server_oci.gateway.server import run_gateway
    except ImportError:
        log.error(
            "mcp_server_oci_not_installed",
            hint="pip install mcp-server-oci",
        )
        sys.exit(1)

    log.info("starting_oci_mcp_gateway", version="1.0.0")
    run_gateway()


if __name__ == "__main__":
    main()
