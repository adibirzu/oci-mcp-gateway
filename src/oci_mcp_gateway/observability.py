"""OpenTelemetry initialization for OCI APM + Log Analytics.

Sends traces to OCI APM domain and configures structured logging
for collection by the OCI Logging Agent running as a DaemonSet.
"""

from __future__ import annotations

import os

import structlog

log = structlog.get_logger(__name__)


def init_otel() -> None:
    """Initialize OTEL tracing with OCI APM exporter."""
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "oci-mcp-gateway"),
            "service.version": "1.0.0",
            "deployment.environment": os.getenv("OTEL_ENVIRONMENT", "production"),
        }
    )

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    apm_key = os.getenv("OCI_APM_DATA_KEY", "")

    headers = {}
    if apm_key:
        headers["Authorization"] = f"dataKey {apm_key}"

    exporter = OTLPSpanExporter(
        endpoint=f"{endpoint}/20200101/opentelemetry/private/v1/traces",
        headers=headers,
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    log.info(
        "otel_tracing_configured",
        service="oci-mcp-gateway",
        endpoint=endpoint,
    )
