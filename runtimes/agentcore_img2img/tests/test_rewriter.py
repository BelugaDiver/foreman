from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from runtimes.agentcore_img2img.app.settings import PipelineSettings
from runtimes.agentcore_img2img.app.stages.rewriter import RewriteResult, rewrite_prompt


def _make_settings(**overrides) -> PipelineSettings:
    defaults = dict(
        prompt_rewrite_model_id="google.gemma-3-12b-it",
        sd_model_id="us.stability.stable-image-control-structure-v1:0",
        controlnet_mode="depth",
        verification_alignment_threshold=0.75,
        verification_max_iterations=3,
        verification_time_budget_seconds=120.0,
        verification_iter_estimate_seconds=30.0,
        max_output_image_bytes=1048576,
        sd_prompt_max_tokens=500,
        correction_context_max_tokens=300,
        aws_region="us-east-1",
    )
    defaults.update(overrides)
    return PipelineSettings(**defaults)


def _fake_image_b64() -> str:
    return base64.b64encode(b"\xff\xd8\xff\xe0fake_image_data").decode()


def _make_invoke_gemma_side_effect(text: str):
    """Return a side-effect function that patches _invoke_gemma to return ``text``."""

    def side_effect(**kwargs):
        return text

    return side_effect


@pytest.fixture()
def settings() -> PipelineSettings:
    return _make_settings()


async def test_happy_path_returns_enriched_prompt(settings: PipelineSettings) -> None:
    enriched = "A bright modern living room with oak floors and a vaulted ceiling"

    with patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._invoke_gemma",
        side_effect=_make_invoke_gemma_side_effect(enriched),
    ), patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._build_bedrock_client",
        return_value=MagicMock(),
    ):
        result = await rewrite_prompt(
            original_prompt="modern living room",
            image_b64=_fake_image_b64(),
            image_format="jpeg",
            settings=settings,
        )

    assert isinstance(result, RewriteResult)
    assert result.enriched_prompt == enriched
    assert result.model_id == "google.gemma-3-12b-it"
    assert result.latency_ms >= 0


async def test_empty_model_output_substitutes_original_prompt(settings: PipelineSettings) -> None:
    with patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._invoke_gemma",
        side_effect=_make_invoke_gemma_side_effect("   "),
    ), patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._build_bedrock_client",
        return_value=MagicMock(),
    ):
        result = await rewrite_prompt(
            original_prompt="my original prompt",
            image_b64=_fake_image_b64(),
            image_format="jpeg",
            settings=settings,
        )

    assert result.enriched_prompt == "my original prompt"


async def test_prompt_truncated_to_sd_prompt_max_tokens(settings: PipelineSettings) -> None:
    long_output = "A" * 1000  # exceeds default 500-char limit

    with patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._invoke_gemma",
        side_effect=_make_invoke_gemma_side_effect(long_output),
    ), patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._build_bedrock_client",
        return_value=MagicMock(),
    ):
        result = await rewrite_prompt(
            original_prompt="any prompt",
            image_b64=_fake_image_b64(),
            image_format="jpeg",
            settings=settings,
        )

    assert len(result.enriched_prompt) == settings.sd_prompt_max_tokens


async def test_correction_context_truncated_and_included(settings: PipelineSettings) -> None:
    """Correction context longer than limit is truncated and appended to the user message."""
    captured_kwargs: dict = {}

    def capture_invoke(**kwargs):
        captured_kwargs.update(kwargs)
        return "refined prompt"

    long_correction = "C" * 1000  # exceeds correction_context_max_tokens=300

    with patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._invoke_gemma",
        side_effect=capture_invoke,
    ), patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._build_bedrock_client",
        return_value=MagicMock(),
    ):
        await rewrite_prompt(
            original_prompt="a prompt",
            image_b64=_fake_image_b64(),
            image_format="jpeg",
            settings=settings,
            correction_context=long_correction,
        )

    user_content = captured_kwargs["user_message_content"]
    # Last element should be the correction context text item
    correction_item = user_content[-1]
    assert "text" in correction_item
    trimmed_context = correction_item["text"]
    # Verify the context was truncated to correction_context_max_tokens
    assert len(trimmed_context) <= settings.correction_context_max_tokens + 100  # includes preamble
    assert "C" * settings.correction_context_max_tokens in trimmed_context


async def test_bedrock_error_propagates(settings: PipelineSettings) -> None:
    with patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._invoke_gemma",
        side_effect=RuntimeError("Bedrock unavailable"),
    ), patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._build_bedrock_client",
        return_value=MagicMock(),
    ):
        with pytest.raises(RuntimeError, match="Bedrock unavailable"):
            await rewrite_prompt(
                original_prompt="a prompt",
                image_b64=_fake_image_b64(),
                image_format="jpeg",
                settings=settings,
            )


async def test_json_output_populates_all_fields(settings: PipelineSettings) -> None:
    """When Gemma returns valid JSON, all three fields are parsed correctly."""
    json_response = json.dumps({
        "positive_prompt": "A bright Scandi living room with oak floors",
        "negative_prompt": "dark, cluttered, ornate, maximalist",
        "elements": ["sofa → low-profile linen sectional", "rug → natural jute"],
    })

    with patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._invoke_gemma",
        side_effect=_make_invoke_gemma_side_effect(json_response),
    ), patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._build_bedrock_client",
        return_value=MagicMock(),
    ):
        result = await rewrite_prompt(
            original_prompt="scandi living room",
            image_b64=_fake_image_b64(),
            image_format="jpeg",
            settings=settings,
        )

    assert result.positive_prompt == "A bright Scandi living room with oak floors"
    assert result.negative_prompt == "dark, cluttered, ornate, maximalist"
    assert result.elements == ["sofa → low-profile linen sectional", "rug → natural jute"]
    # enriched_prompt is an alias for positive_prompt
    assert result.enriched_prompt == result.positive_prompt


async def test_markdown_fenced_json_is_stripped_and_parsed(settings: PipelineSettings) -> None:
    """Gemma sometimes wraps the JSON in ```json fences; these should be stripped."""
    fenced = "```json\n" + json.dumps({
        "positive_prompt": "Industrial loft with exposed brick",
        "negative_prompt": "pastel, floral",
        "elements": ["shelves → black steel open shelving"],
    }) + "\n```"

    with patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._invoke_gemma",
        side_effect=_make_invoke_gemma_side_effect(fenced),
    ), patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._build_bedrock_client",
        return_value=MagicMock(),
    ):
        result = await rewrite_prompt(
            original_prompt="industrial loft",
            image_b64=_fake_image_b64(),
            image_format="jpeg",
            settings=settings,
        )

    assert result.positive_prompt == "Industrial loft with exposed brick"
    assert result.elements == ["shelves → black steel open shelving"]


async def test_json_missing_fields_fall_back_gracefully(settings: PipelineSettings) -> None:
    """Partial JSON (missing negative_prompt and elements) falls back to safe defaults."""
    partial_json = json.dumps({"positive_prompt": "A cosy bedroom"})

    with patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._invoke_gemma",
        side_effect=_make_invoke_gemma_side_effect(partial_json),
    ), patch(
        "runtimes.agentcore_img2img.app.stages.rewriter._build_bedrock_client",
        return_value=MagicMock(),
    ):
        result = await rewrite_prompt(
            original_prompt="cosy bedroom",
            image_b64=_fake_image_b64(),
            image_format="jpeg",
            settings=settings,
        )

    assert result.positive_prompt == "A cosy bedroom"
    assert result.negative_prompt == ""
    assert result.elements == []
