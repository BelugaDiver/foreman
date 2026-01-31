"""OpenTelemetry configuration for Foreman."""

import logging
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def setup_telemetry(
    service_name: str = "foreman",
    otlp_endpoint: Optional[str] = None,
    insecure: bool = True,
) -> None:
    """
    Setup OpenTelemetry instrumentation.

    Args:
        service_name: Name of the service for tracing
        otlp_endpoint: OTLP endpoint URL (e.g., "http://localhost:4317")
                      If None, telemetry will be configured but not exported
        insecure: If True, disables TLS verification for OTLP exporter.
                 Should be False in production with proper certificates.
    """
    # Create a resource with service name
    resource = Resource.create({"service.name": service_name})

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Add OTLP exporter if endpoint is provided
    if otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=insecure)
        processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(processor)
        logger.info(f"OpenTelemetry configured with OTLP endpoint: {otlp_endpoint}")
    else:
        logger.info("OpenTelemetry configured without OTLP exporter")

    # Set global tracer provider
    trace.set_tracer_provider(provider)


def instrument_app(app) -> None:
    """
    Instrument FastAPI app with OpenTelemetry.

    Args:
        app: FastAPI application instance
    """
    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI instrumented with OpenTelemetry")
