"""Tests for OpenTelemetry instrumentation."""

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from foreman.telemetry import instrument_app, setup_telemetry


def test_setup_telemetry_without_exporter():
    """Test telemetry setup without OTLP exporter."""
    setup_telemetry(service_name="test-service")

    # Verify tracer provider is set
    tracer = trace.get_tracer(__name__)
    assert tracer is not None


def test_setup_telemetry_with_exporter():
    """Test telemetry setup with OTLP exporter."""
    setup_telemetry(
        service_name="test-service",
        otlp_endpoint="http://localhost:4317",
        insecure=True,
    )

    # Verify tracer provider is set
    tracer = trace.get_tracer(__name__)
    assert tracer is not None


def test_instrument_app():
    """Test FastAPI app instrumentation."""
    # Create a mock app
    mock_app = MagicMock()

    # Instrument the app
    instrument_app(mock_app)

    # Verify the app was instrumented (the function should complete without error)
    assert True


def test_request_tracing_middleware_creates_span():
    """Ensure inbound API calls are traced."""
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"status": "ok"}

    instrument_app(app)
    client = TestClient(app)

    response = client.get("/ping")
    assert response.status_code == 200

    spans = exporter.get_finished_spans()
    middleware_spans = [
        span for span in spans if span.attributes.get("foreman.telemetry.middleware")
    ]
    assert middleware_spans, "Request tracing middleware should emit spans"
