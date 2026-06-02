from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import runtimes.agentcore_img2img.app.graph as graph_module
from runtimes.agentcore_img2img.app.graph import run_graph


def test_run_graph_without_image(monkeypatch) -> None:
    """run_graph with no image returns valid metadata without attempting a fetch."""
    monkeypatch.setenv("RUNTIME_OUTPUT_BASE_URL", "https://cdn.example.com/generated")
    monkeypatch.setattr(graph_module, "_AGENT", None)

    result = run_graph(
        generation_id="gen-1",
        prompt="a watercolor landscape",
        input_image_url=None,
        style_id=None,
    )

    assert result["output_image_url"] == "https://cdn.example.com/generated/gen-1.png"
    assert "watercolor landscape" in result["generated_image_description"]


def test_run_graph_fetches_and_forwards_image_to_agent(monkeypatch) -> None:
    """run_graph fetches image bytes and passes them to the agent as multimodal input."""
    monkeypatch.setenv("RUNTIME_OUTPUT_BASE_URL", "https://cdn.example.com/generated")

    fake_image_bytes = b"\x89PNG\r\n\x1a\n"
    mock_response = MagicMock()
    mock_response.content = fake_image_bytes
    mock_response.headers = {"content-type": "image/png"}
    mock_response.raise_for_status = MagicMock()

    mock_agent = MagicMock(return_value="A landscape transformed into watercolor style.")
    monkeypatch.setattr(graph_module, "_AGENT", mock_agent)

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=mock_response):
        result = run_graph(
            generation_id="gen-2",
            prompt="watercolor style",
            input_image_url="https://cdn.example.com/input.png",
            style_id=None,
        )

    assert result["output_image_url"] == "https://cdn.example.com/generated/gen-2.png"

    call_args = mock_agent.call_args[0][0]
    assert isinstance(call_args, list)
    image_block = next(b for b in call_args if "image" in b)
    assert image_block["image"]["format"] == "png"
    assert image_block["image"]["source"]["bytes"] == fake_image_bytes


def test_run_graph_format_detected_from_url_extension(monkeypatch) -> None:
    """Format falls back to URL extension when Content-Type is absent or unrecognised."""
    monkeypatch.setenv("RUNTIME_OUTPUT_BASE_URL", "https://cdn.example.com/generated")

    mock_response = MagicMock()
    mock_response.content = b"JFIF"
    mock_response.headers = {"content-type": "application/octet-stream"}
    mock_response.raise_for_status = MagicMock()

    mock_agent = MagicMock(return_value="desc")
    monkeypatch.setattr(graph_module, "_AGENT", mock_agent)

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=mock_response):
        run_graph(
            generation_id="gen-ext",
            prompt="test",
            input_image_url="https://cdn.example.com/photo.jpg",
            style_id=None,
        )

    call_args = mock_agent.call_args[0][0]
    image_block = next(b for b in call_args if "image" in b)
    assert image_block["image"]["format"] == "jpeg"


def test_run_graph_image_fetch_failure_falls_back_gracefully(monkeypatch) -> None:
    """run_graph continues without image data if the fetch fails."""
    monkeypatch.setenv("RUNTIME_OUTPUT_BASE_URL", "https://cdn.example.com/generated")
    monkeypatch.setattr(graph_module, "_AGENT", None)

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", side_effect=Exception("timeout")):
        result = run_graph(
            generation_id="gen-3",
            prompt="portrait",
            input_image_url="https://cdn.example.com/input.png",
            style_id="noir",
        )

    assert result["output_image_url"] == "https://cdn.example.com/generated/gen-3.png"
    assert "portrait" in result["generated_image_description"]
    assert "noir" in result["generated_image_description"]


def test_run_graph_raises_without_output_base_url(monkeypatch) -> None:
    """run_graph raises ValueError when RUNTIME_OUTPUT_BASE_URL is not configured."""
    monkeypatch.delenv("RUNTIME_OUTPUT_BASE_URL", raising=False)
    monkeypatch.setattr(graph_module, "_AGENT", None)

    with pytest.raises(ValueError, match="RUNTIME_OUTPUT_BASE_URL"):
        run_graph(
            generation_id="gen-4",
            prompt="test",
            input_image_url=None,
            style_id=None,
        )
