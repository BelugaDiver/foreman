from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest

import runtimes.agentcore_img2img.app.graph as graph_module
from runtimes.agentcore_img2img.app.graph import run_graph


def _bedrock_response(text: str) -> dict:
    """Build a minimal Bedrock invoke_model response dict."""
    body = json.dumps({"choices": [{"message": {"content": text}}]}).encode()
    return {"body": io.BytesIO(body)}


def test_run_graph_without_image(monkeypatch) -> None:
    """run_graph with no image returns valid metadata without attempting a fetch."""
    monkeypatch.setenv("RUNTIME_OUTPUT_BASE_URL", "https://cdn.example.com/generated")
    monkeypatch.setattr(graph_module, "_BEDROCK", None)

    result = run_graph(
        generation_id="gen-1",
        prompt="a watercolor landscape",
        input_image_url=None,
        style_id=None,
    )

    assert result["output_image_url"] == "https://cdn.example.com/generated/gen-1.png"
    assert "watercolor landscape" in result["generated_image_description"]


def test_run_graph_fetches_and_forwards_image_to_agent(monkeypatch) -> None:
    """run_graph fetches image bytes and passes them to Bedrock as multimodal input."""
    monkeypatch.setenv("RUNTIME_OUTPUT_BASE_URL", "https://cdn.example.com/generated")
    monkeypatch.setattr(graph_module, "_STRANDS_MODEL_ID", "test-model")

    fake_image_bytes = b"fake-image"
    resized_jpeg = b"resized-jpeg"
    mock_http = MagicMock()
    mock_http.content = fake_image_bytes
    mock_http.headers = {"content-type": "image/png"}
    mock_http.raise_for_status = MagicMock()

    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = _bedrock_response(
        "A landscape transformed into watercolor style."
    )
    monkeypatch.setattr(graph_module, "_BEDROCK", mock_bedrock)
    # Bypass PIL so tests don't need a real image file
    monkeypatch.setattr(graph_module, "_resize_image", MagicMock(return_value=(resized_jpeg, "jpeg")))

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=mock_http):
        result = run_graph(
            generation_id="gen-2",
            prompt="watercolor style",
            input_image_url="https://cdn.example.com/input.png",
            style_id=None,
        )

    assert result["output_image_url"] == "https://cdn.example.com/generated/gen-2.png"
    assert result["generated_image_description"] == "A landscape transformed into watercolor style."

    call_kwargs = mock_bedrock.invoke_model.call_args.kwargs
    body = json.loads(call_kwargs["body"])
    user_content = body["messages"][1]["content"]
    assert isinstance(user_content, list)
    image_block = next(b for b in user_content if b.get("type") == "image_url")
    assert image_block["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_run_graph_format_detected_from_url_extension(monkeypatch) -> None:
    """Format falls back to URL extension when Content-Type is absent or unrecognised."""
    monkeypatch.setenv("RUNTIME_OUTPUT_BASE_URL", "https://cdn.example.com/generated")
    monkeypatch.setattr(graph_module, "_STRANDS_MODEL_ID", "test-model")

    mock_http = MagicMock()
    mock_http.content = b"JFIF"
    mock_http.headers = {"content-type": "application/octet-stream"}
    mock_http.raise_for_status = MagicMock()

    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = _bedrock_response("desc")
    monkeypatch.setattr(graph_module, "_BEDROCK", mock_bedrock)
    monkeypatch.setattr(graph_module, "_resize_image", MagicMock(return_value=(b"JFIF", "jpeg")))

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=mock_http):
        run_graph(
            generation_id="gen-ext",
            prompt="test",
            input_image_url="https://cdn.example.com/photo.jpg",
            style_id=None,
        )

    # Verify Bedrock was called — format was detected from .jpg extension
    assert mock_bedrock.invoke_model.called
    body = json.loads(mock_bedrock.invoke_model.call_args.kwargs["body"])
    user_content = body["messages"][1]["content"]
    image_block = next(b for b in user_content if b.get("type") == "image_url")
    assert "data:image/jpeg;base64," in image_block["image_url"]["url"]


def test_run_graph_image_fetch_failure_falls_back_gracefully(monkeypatch) -> None:
    """run_graph continues without image data if the fetch fails."""
    monkeypatch.setenv("RUNTIME_OUTPUT_BASE_URL", "https://cdn.example.com/generated")
    monkeypatch.setattr(graph_module, "_BEDROCK", None)

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
    monkeypatch.setattr(graph_module, "_BEDROCK", None)

    with pytest.raises(ValueError, match="RUNTIME_OUTPUT_BASE_URL"):
        run_graph(
            generation_id="gen-4",
            prompt="test",
            input_image_url=None,
            style_id=None,
        )
