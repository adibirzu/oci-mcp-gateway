"""Standalone HTTP health endpoints for Kubernetes probes.

These run as a lightweight ASGI app alongside the MCP gateway,
providing /health and /ready endpoints that K8s liveness and
readiness probes can hit without MCP session overhead.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# Global reference set by gateway startup
_registry: Any = None
_start_time: float = time.time()


def set_registry(registry: Any) -> None:
    """Register the BackendRegistry for health checks."""
    global _registry
    _registry = registry


async def health_check() -> dict[str, Any]:
    """Liveness probe — returns 200 if the process is running."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "version": "1.0.0",
    }


async def readiness_check() -> dict[str, Any]:
    """Readiness probe — returns 200 only if at least one backend is healthy."""
    if _registry is None:
        return {"status": "not_ready", "reason": "registry_not_initialized"}

    summary = _registry.get_health_summary()
    healthy = summary.get("healthy", 0)
    total = summary.get("total", 0)

    if healthy == 0 and total > 0:
        return {
            "status": "not_ready",
            "reason": "no_healthy_backends",
            "total": total,
            "healthy": healthy,
        }

    return {
        "status": "ready",
        "total": total,
        "healthy": healthy,
        "backends": summary.get("backends", {}),
    }
