"""Gateway application builder.

Bridges this OKE wrapper with the production gateway engine
(``mcp_server_oci.gateway``). The engine's ``run_gateway()`` builds *and*
serves in one blocking call, leaving no seam to attach Kubernetes probe
routes or register the backend registry for health checks.

This module drops one level down to the engine's build/serve split:

    create_gateway(config)   -> build the FastMCP app (+ backend registry)
    <wire /health, /ready>   -> attach our ASGI probe routes here
    gateway.run(...)         -> serve (blocking)

The probe routes are mounted on the *same* FastMCP/uvicorn app as ``/mcp``,
so a single port (9000) serves both the MCP protocol and the K8s probes.
"""

from __future__ import annotations

from typing import Any

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse

from oci_mcp_gateway import health

log = structlog.get_logger(__name__)

# HTTP status returned to Kubernetes probes.
_HTTP_OK = 200
_HTTP_UNAVAILABLE = 503


def build_gateway(config: Any | None = None) -> tuple[Any, Any]:
    """Build the gateway FastMCP app with K8s probe routes wired in.

    Returns the ``(gateway, config)`` pair so the caller can start the
    blocking server with the engine's expected run kwargs.
    """
    from mcp_server_oci.gateway.config import load_gateway_config
    from mcp_server_oci.gateway.server import create_gateway

    if config is None:
        config = load_gateway_config()

    gateway = create_gateway(config)

    # The engine stores the live BackendRegistry on the FastMCP instance.
    # Hand it to our health module so /ready reflects real backend state.
    registry = getattr(gateway, "_gateway_registry", None)
    if registry is None:
        log.warning("gateway_registry_missing", hint="readiness will report not_ready")
    else:
        health.set_registry(registry)

    _register_probe_routes(gateway)
    log.info("probe_routes_registered", routes=["/health", "/ready"])

    return gateway, config


def _register_probe_routes(gateway: Any) -> None:
    """Attach /health (liveness) and /ready (readiness) to the FastMCP app."""

    @gateway.custom_route("/health", methods=["GET"])
    async def _health(_request: Request) -> JSONResponse:
        # Liveness: process is up. Always 200 unless the process is wedged.
        return JSONResponse(await health.health_check(), status_code=_HTTP_OK)

    @gateway.custom_route("/ready", methods=["GET"])
    async def _ready(_request: Request) -> JSONResponse:
        # Readiness: 200 only when the registry reports a healthy backend.
        result = await health.readiness_check()
        ready = result.get("status") == "ready"
        return JSONResponse(
            result, status_code=_HTTP_OK if ready else _HTTP_UNAVAILABLE
        )


def run(gateway: Any, config: Any) -> None:
    """Serve the gateway with the same run kwargs the engine uses."""
    run_kwargs: dict[str, Any] = {
        "transport": "streamable-http",
        "host": config.host,
        "port": config.port,
        "path": config.path,
    }
    if getattr(config, "stateless", False):
        run_kwargs["stateless_http"] = True

    log.info(
        "starting_oci_mcp_gateway",
        host=config.host,
        port=config.port,
        path=config.path,
        backends=len(config.get_enabled_backends()),
        auth_enabled=config.auth.enabled,
    )
    gateway.run(**run_kwargs)
