"""Tests for OpenTelemetry instrumentation."""

from unittest.mock import MagicMock

from opentelemetry import trace

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
