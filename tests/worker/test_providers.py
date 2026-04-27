"""Tests for worker/providers/__init__.py."""

import pytest

from worker.providers import GeminiProvider, get_provider


def test_get_provider_vertex_returns_gemini_provider():
    """get_provider('vertex') returns a GeminiProvider instance."""
    provider = get_provider("vertex")
    assert isinstance(provider, GeminiProvider)


def test_get_provider_vertex_passes_kwargs():
    """kwargs are forwarded to GeminiProvider.__init__."""
    provider = get_provider("vertex", project_id="my-project", location="europe-west4")
    assert provider.project_id == "my-project"
    assert provider.location == "europe-west4"


def test_get_provider_unknown_raises():
    """Unknown provider type raises ValueError."""
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider("unsupported")
