"""OpenTelemetry configuration for Foreman."""

import logging
from typing import Optional

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def setup_telemetry(
    service_name: str = "foreman",
    otlp_endpoint: Optional[str] = None,
    insecure: bool = True,
    service_version: Optional[str] = None,
) -> None:
    """Configure the global tracer provider and OTLP exporter."""
    resource_attributes = {"service.name": service_name}
    if service_version:
        resource_attributes["service.version"] = service_version

    resource = Resource.create(resource_attributes)
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OpenTelemetry exporting to %s", otlp_endpoint)
    else:
        logger.warning("OTLP endpoint not provided; spans will not be exported")


def instrument_app(app: FastAPI) -> None:
    """Instrument a FastAPI app using the official OpenTelemetry instrumentor."""
    flag_name = "_foreman_otel_instrumented"
    if getattr(app.state, flag_name, False):
        logger.debug("FastAPI app already instrumented")
        return

    FastAPIInstrumentor().instrument_app(app)
    app.state.__setattr__(flag_name, True)
    logger.info("FastAPI instrumented with OpenTelemetry")
