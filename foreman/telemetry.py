"""OpenTelemetry configuration for Foreman."""

import logging
from typing import Optional

from fastapi import Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

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
    resource = Resource(attributes={
        "service.name": service_name
    })

    # Create tracer provider
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # Add OTLP exporter if endpoint is provided
    if otlp_endpoint:
        # otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=insecure)
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(processor)
        # trace.get_tracer_provider().add_span_processor(processor)
        logger.info(f"OpenTelemetry configured with OTLP endpoint: {otlp_endpoint}")
    else:
        logger.info("OpenTelemetry configured without OTLP exporter")



def instrument_app(app) -> None:
    """Instrument FastAPI app with OpenTelemetry."""
    FastAPIInstrumentor.instrument_app(app, tracer_provider=trace.get_tracer_provider())
    _enable_request_tracing(app)
    logger.info("FastAPI instrumented with OpenTelemetry")


def _enable_request_tracing(app) -> None:
    """Attach middleware that traces every inbound API call."""
    flag_name = "_foreman_request_tracing"
    if getattr(app.state, flag_name, False):
        return

    tracer = trace.get_tracer(__name__)

    @app.middleware("http")
    async def _trace_requests(request: Request, call_next):  # type: ignore[arg-type]
        span_name = f"{request.method} {request.url.path}"
        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", request.url.path)
            span.set_attribute("http.url", str(request.url))
            if request.client:
                span.set_attribute("http.client_ip", request.client.host)
            span.set_attribute("foreman.telemetry.middleware", True)

            response = await call_next(request)
            span.set_attribute("http.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            return response

    app.state.__setattr__(flag_name, True)
    logger.info("Request tracing middleware enabled")
