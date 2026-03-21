"""OpenTelemetry initialization for OCI APM — traces + metrics.

Follows the multillm pattern: dual-endpoint support (OCI APM or standard OTLP),
per-tool-call OTEL spans created by the guardrail middleware, and metrics
counters for tool calls and latency visible in the OCI APM dashboard.

Supports two destinations:
- OCI APM: Set OTEL_EXPORTER_OTLP_ENDPOINT + OCI_APM_DATA_KEY
- Standard OTLP: Set OTEL_EXPORTER_OTLP_ENDPOINT only
"""

from __future__ import annotations

import os

import structlog

log = structlog.get_logger(__name__)


def init_otel() -> None:
    """Initialize OTEL tracing and metrics with OCI APM exporter."""
    from opentelemetry import trace, metrics
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    service_name = os.getenv("OTEL_SERVICE_NAME", "oci-mcp-gateway")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    apm_key = os.getenv("OCI_APM_DATA_KEY", "")

    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("OTEL_ENVIRONMENT", "production"),
        "service.namespace": "oci-mcp",
    })

    # Build exporter kwargs — OCI APM uses dataKey auth header
    headers: dict[str, str] = {}
    if apm_key:
        headers["Authorization"] = f"dataKey {apm_key}"

    trace_endpoint = f"{endpoint}/20200101/opentelemetry/private/v1/traces"
    exporter_kwargs = {"endpoint": trace_endpoint, "headers": headers}

    # ── Tracing ──────────────────────────────────────────────────────
    trace_exporter = OTLPSpanExporter(**exporter_kwargs)
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(tp)

    # ── Metrics ──────────────────────────────────────────────────────
    # OCI APM uses a separate metrics endpoint path
    metrics_endpoint = trace_endpoint.replace(
        "/opentelemetry/private/v1/traces",
        "/opentelemetry/private/v1/metrics",
    )
    metrics_kwargs = {"endpoint": metrics_endpoint, "headers": headers}

    metric_exporter = OTLPMetricExporter(**metrics_kwargs)
    reader = PeriodicExportingMetricReader(
        metric_exporter, export_interval_millis=30000
    )
    mp = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(mp)

    dest = "OCI APM" if apm_key else "standard OTLP"
    log.info(
        "otel_initialized",
        service=service_name,
        destination=dest,
        endpoint=endpoint,
        traces=True,
        metrics=True,
    )
