"""
otel_setup.py — OpenTelemetry bootstrap shared by all three services (Phase 2).

Configures the THREE signals and exports them to the OTel Collector over OTLP
gRPC (:4317):
  - traces   : auto-instrumented FastAPI (server) + httpx (client, where present),
               with W3C context propagation so the cascade is ONE connected trace.
  - metrics  : process/system CPU & memory (SystemMetrics) + HTTP request metrics
               from the FastAPI/httpx instrumentation.
  - logs     : Python logging bridged to OTLP; records emitted inside a request
               automatically carry trace_id/span_id (structured + correlated).

`service.name` (the resource attribute) is the key the RCA later attributes to,
so it is set explicitly per service via OTEL_SERVICE_NAME.
"""
import logging
import os

from opentelemetry import trace, metrics
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor


def setup_telemetry(app, service_name: str | None = None):
    service_name = service_name or os.getenv("OTEL_SERVICE_NAME", "unknown-service")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    resource = Resource.create({SERVICE_NAME: service_name})

    # ---- traces ----
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # ---- metrics ----
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=10000,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    # ---- logs ----
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(logger_provider)
    otlp_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(otlp_handler)

    # ---- auto-instrumentation ----
    FastAPIInstrumentor.instrument_app(app)          # HTTP server spans + metrics
    try:                                             # httpx client (orders/frontend only)
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except Exception:                                # payments has no httpx -> skip
        pass
    SystemMetricsInstrumentor().instrument()         # process CPU / memory

    return trace.get_tracer(service_name)
