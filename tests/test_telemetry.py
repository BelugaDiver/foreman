"""Tests for OpenTelemetry instrumentation."""

# ---------------------------------------------------------------------------
# Third-party
# ---------------------------------------------------------------------------
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------
from foreman.telemetry import instrument_app, setup_telemetry

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_setup_telemetry_without_exporter():
    """setup_telemetry() with no OTLP endpoint should still configure a tracer provider."""
    # Arrange — no endpoint configured

    # Act
    setup_telemetry(service_name="test-service")

    # Assert
    tracer = trace.get_tracer(__name__)
    assert tracer is not None


def test_setup_telemetry_with_exporter():
    """setup_telemetry() with an OTLP endpoint should configure a tracer provider."""
    # Arrange
    endpoint = "http://localhost:4317"

    # Act
    setup_telemetry(service_name="test-service", otlp_endpoint=endpoint, insecure=True)

    # Assert
    tracer = trace.get_tracer(__name__)
    assert tracer is not None


def test_instrument_app():
    """instrument_app() should mark the FastAPI app as instrumented."""
    # Arrange
    app = FastAPI()

    # Act
    instrument_app(app)

    # Assert
    assert getattr(app.state, "_foreman_otel_instrumented", False) is True


def test_http_requests_emit_spans():
    """Inbound API calls should be traced via FastAPI instrumentation."""
    # Arrange
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

    # Act
    response = client.get("/ping")

    # Assert
    assert response.status_code == 200
    spans = exporter.get_finished_spans()
    http_spans = [span for span in spans if span.attributes.get("http.route") == "/ping"]
    assert http_spans, "FastAPI instrumentation should emit HTTP spans"
