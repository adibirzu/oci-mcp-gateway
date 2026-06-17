"""Integration tests: probe routes mounted on the live FastMCP ASGI app.

These exercise the build/serve seam — `build_gateway()` must attach
`/health` and `/ready` to the same Starlette app that serves `/mcp`, and
the readiness route must map backend state to the correct HTTP status.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

# These tests require the gateway engine (mcp-server-oci), which is not on
# PyPI. Skip the whole module when it is absent (e.g. lint-only CI lanes).
pytest.importorskip("mcp_server_oci", reason="gateway engine not installed")


def test_health_route_returns_200(built_gateway) -> None:
    gateway, _config = built_gateway
    app = gateway.http_app(transport="streamable-http", path="/mcp")
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"


def test_ready_route_returns_200_for_empty_gateway(built_gateway) -> None:
    gateway, _config = built_gateway
    app = gateway.http_app(transport="streamable-http", path="/mcp")
    with TestClient(app) as client:
        resp = client.get("/ready")
        # Zero configured backends => ready.
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"


def test_registry_is_wired_into_health_module(built_gateway) -> None:
    # build_gateway() must hand the engine's registry to the health module.
    from oci_mcp_gateway import health

    assert health._registry is not None
    summary = health._registry.get_health_summary()
    assert "total" in summary and "healthy" in summary
