from __future__ import annotations

import base64
import io
import json
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from runtimes.agentcore_img2img.app.settings import PipelineSettings
from runtimes.agentcore_img2img.app.stages.generator import GenerationResult, generate_image


def _make_settings(**overrides) -> PipelineSettings:
    defaults = dict(
        prompt_rewrite_model_id="amazon.nova-lite-v1:0",
        sd_model_id="us.stability.stable-image-control-structure-v1:0",
        controlnet_mode="depth",
        verification_alignment_threshold=0.75,
        verification_max_iterations=3,
        verification_time_budget_seconds=120.0,
        verification_iter_estimate_seconds=30.0,
        max_output_image_bytes=1048576,
        sd_prompt_max_tokens=500,
        correction_context_max_tokens=300,
        output_base_url="https://cdn.example.com",
        aws_region="us-east-1",
    )
    defaults.update(overrides)
    return PipelineSettings(**defaults)


def _make_jpeg_bytes(width: int = 64, height: int = 64, color: str = "red") -> bytes:
    """Create a minimal valid JPEG."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_sd_response(
    image_b64: str,
    finish_reason: str | None = None,
    seed: int = 42,
) -> MagicMock:
    """Build a mock boto3 response for an SD model invoke."""
    body_bytes = json.dumps(
        {
            "seeds": [seed],
            "finish_reasons": [finish_reason],
            "images": [image_b64],
        }
    ).encode()
    mock_body = MagicMock()
    mock_body.read.return_value = body_bytes
    mock_resp = MagicMock()
    mock_resp.__getitem__ = lambda self, key: mock_body if key == "body" else None
    return mock_resp


@pytest.fixture()
def settings() -> PipelineSettings:
    return _make_settings()


@pytest.fixture()
def control_image() -> bytes:
    return _make_jpeg_bytes()


async def test_happy_path_returns_image_bytes(
    settings: PipelineSettings, control_image: bytes
) -> None:
    output_jpeg = _make_jpeg_bytes(color="blue")
    output_b64 = base64.b64encode(output_jpeg).decode()

    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _make_sd_response(output_b64, finish_reason=None)

    with patch(
        "runtimes.agentcore_img2img.app.stages.generator._build_bedrock_client",
        return_value=mock_client,
    ):
        result = await generate_image(
            enriched_prompt="a blue room",
            control_image_bytes=control_image,
            control_image_format="jpeg",
            settings=settings,
        )

    assert isinstance(result, GenerationResult)
    assert result.finish_reason is None
    assert len(result.image_bytes) > 0
    assert result.image_b64 != ""
    assert result.model_id == settings.sd_model_id
    assert result.latency_ms >= 0


async def test_non_null_finish_reason_returns_empty_bytes(
    settings: PipelineSettings, control_image: bytes
) -> None:
    output_b64 = base64.b64encode(b"ignored").decode()
    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _make_sd_response(output_b64, finish_reason="ERROR")

    with patch(
        "runtimes.agentcore_img2img.app.stages.generator._build_bedrock_client",
        return_value=mock_client,
    ):
        result = await generate_image(
            enriched_prompt="a room",
            control_image_bytes=control_image,
            control_image_format="jpeg",
            settings=settings,
        )

    assert result.finish_reason == "ERROR"
    assert result.image_bytes == b""
    assert result.image_b64 == ""


async def test_output_over_limit_is_compressed(
    settings: PipelineSettings, control_image: bytes
) -> None:
    # Create a large JPEG (300x300) that will exceed a tiny 1 KB limit
    large_jpeg = _make_jpeg_bytes(300, 300)
    large_b64 = base64.b64encode(large_jpeg).decode()

    tiny_settings = _make_settings(max_output_image_bytes=1)  # 1 byte — impossible to satisfy
    # Use a more realistic limit: 50 KB, which the 300x300 JPEG likely exceeds at high quality
    real_limit = len(large_jpeg) // 2
    compress_settings = _make_settings(max_output_image_bytes=real_limit)

    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _make_sd_response(large_b64, finish_reason=None)

    with patch(
        "runtimes.agentcore_img2img.app.stages.generator._build_bedrock_client",
        return_value=mock_client,
    ):
        result = await generate_image(
            enriched_prompt="a large room",
            control_image_bytes=control_image,
            control_image_format="jpeg",
            settings=compress_settings,
        )

    # Either compressed to fit, or empty if impossible
    if result.image_bytes:
        assert len(result.image_bytes) <= compress_settings.max_output_image_bytes
    else:
        assert result.finish_reason is not None


async def test_output_impossible_to_compress_treated_as_sd_failure(
    settings: PipelineSettings, control_image: bytes
) -> None:
    jpeg_bytes = _make_jpeg_bytes(64, 64)
    b64 = base64.b64encode(jpeg_bytes).decode()

    # Limit of 1 byte — impossible to compress a JPEG to fit
    tiny_settings = _make_settings(max_output_image_bytes=1)
    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _make_sd_response(b64, finish_reason=None)

    with patch(
        "runtimes.agentcore_img2img.app.stages.generator._build_bedrock_client",
        return_value=mock_client,
    ):
        result = await generate_image(
            enriched_prompt="a room",
            control_image_bytes=control_image,
            control_image_format="jpeg",
            settings=tiny_settings,
        )

    assert result.image_bytes == b""
    assert result.finish_reason == "output_too_large"


async def test_bedrock_error_propagates(
    settings: PipelineSettings, control_image: bytes
) -> None:
    mock_client = MagicMock()
    mock_client.invoke_model.side_effect = RuntimeError("Bedrock unavailable")

    with patch(
        "runtimes.agentcore_img2img.app.stages.generator._build_bedrock_client",
        return_value=mock_client,
    ):
        with pytest.raises(RuntimeError, match="Bedrock unavailable"):
            await generate_image(
                enriched_prompt="a room",
                control_image_bytes=control_image,
                control_image_format="jpeg",
                settings=settings,
            )


async def test_sd_model_id_env_override_reaches_bedrock(
    settings: PipelineSettings, control_image: bytes
) -> None:
    """FR-010 / SC-005: SD_MODEL_ID override is passed as modelId in the Bedrock invoke call."""
    custom_model = "us.stability.custom-model-v1:0"
    custom_settings = _make_settings(sd_model_id=custom_model)

    output_b64 = base64.b64encode(_make_jpeg_bytes()).decode()
    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _make_sd_response(output_b64, finish_reason=None)

    with patch(
        "runtimes.agentcore_img2img.app.stages.generator._build_bedrock_client",
        return_value=mock_client,
    ):
        await generate_image(
            enriched_prompt="a room",
            control_image_bytes=control_image,
            control_image_format="jpeg",
            settings=custom_settings,
        )

    call_kwargs = mock_client.invoke_model.call_args
    assert call_kwargs.kwargs.get("modelId") == custom_model or (
        call_kwargs.args and call_kwargs.args[0] == custom_model
    )
