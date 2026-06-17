"""Unit tests for the standalone health/readiness logic."""

from __future__ import annotations

import pytest

from oci_mcp_gateway import health


@pytest.mark.asyncio
async def test_health_check_reports_ok_and_uptime() -> None:
    result = await health.health_check()
    assert result["status"] == "ok"
    assert result["uptime_seconds"] >= 0
    assert "version" in result


@pytest.mark.asyncio
async def test_readiness_not_ready_when_registry_uninitialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health, "_registry", None, raising=False)
    result = await health.readiness_check()
    assert result["status"] == "not_ready"
    assert result["reason"] == "registry_not_initialized"


@pytest.mark.asyncio
async def test_readiness_not_ready_when_no_healthy_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Registry:
        def get_health_summary(self) -> dict:
            return {"total": 3, "healthy": 0, "backends": {}}

    monkeypatch.setattr(health, "_registry", _Registry(), raising=False)
    result = await health.readiness_check()
    assert result["status"] == "not_ready"
    assert result["reason"] == "no_healthy_backends"
    assert result["total"] == 3


@pytest.mark.asyncio
async def test_readiness_ready_when_a_backend_is_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Registry:
        def get_health_summary(self) -> dict:
            return {"total": 2, "healthy": 1, "backends": {"logan": {"status": "healthy"}}}

    monkeypatch.setattr(health, "_registry", _Registry(), raising=False)
    result = await health.readiness_check()
    assert result["status"] == "ready"
    assert result["healthy"] == 1


@pytest.mark.asyncio
async def test_readiness_ready_when_empty_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A gateway with zero configured backends is considered ready.
    class _Registry:
        def get_health_summary(self) -> dict:
            return {"total": 0, "healthy": 0, "backends": {}}

    monkeypatch.setattr(health, "_registry", _Registry(), raising=False)
    result = await health.readiness_check()
    assert result["status"] == "ready"
