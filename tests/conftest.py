"""Shared pytest fixtures for the gateway wrapper tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

MINIMAL_CONFIG: dict[str, Any] = {
    "name": "oci-mcp-gateway-test",
    "version": "1.0.0",
    "host": "127.0.0.1",
    "port": 9000,
    "path": "/mcp",
    "stateless": True,
    "auth": {"enabled": False, "cors_origins": []},
    "backends": [],
    "enable_audit_log": True,
    "enable_metrics": False,
}


@pytest.fixture
def gateway_config_file(tmp_path: Path) -> Path:
    """Write a minimal, backend-free gateway config and return its path."""
    path = tmp_path / "gateway.json"
    path.write_text(json.dumps(MINIMAL_CONFIG))
    return path


@pytest.fixture
def built_gateway(gateway_config_file: Path, monkeypatch: pytest.MonkeyPatch):
    """Build the gateway app with health probes wired in."""
    monkeypatch.setenv("MCP_GATEWAY_CONFIG", str(gateway_config_file))
    # Reset the module-global registry between tests for isolation.
    from oci_mcp_gateway import health

    monkeypatch.setattr(health, "_registry", None, raising=False)

    from oci_mcp_gateway.app import build_gateway

    gateway, config = build_gateway()
    return gateway, config
