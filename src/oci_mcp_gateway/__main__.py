"""OCI MCP Gateway entry point.

Wraps the ``mcp-server-oci`` gateway engine. Adds:

- OKE-friendly ``/health`` and ``/ready`` HTTP probes on the gateway port.
- Optional OpenTelemetry export to OCI APM (or any OTLP endpoint).

before delegating to the production-grade gateway infrastructure.
"""

from __future__ import annotations

import os
import sys

import structlog

log = structlog.get_logger(__name__)


def main() -> None:
    """Init observability, build the gateway with probes, then serve."""
    # Init observability before anything else (only if an endpoint is set).
    apm_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if apm_endpoint:
        try:
            from oci_mcp_gateway.observability import init_otel

            init_otel()
            log.info("otel_initialized", endpoint=apm_endpoint)
        except ImportError:
            log.warning(
                "otel_packages_not_installed",
                hint="pip install oci-mcp-gateway[otel]",
            )

    try:
        from oci_mcp_gateway.app import build_gateway, run
    except ImportError:
        log.error(
            "mcp_server_oci_not_installed",
            hint="pip install mcp-server-oci",
        )
        sys.exit(1)

    gateway, config = build_gateway()
    run(gateway, config)


if __name__ == "__main__":
    main()
