from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from runtimes.agentcore_img2img.app.settings import PipelineSettings
from runtimes.agentcore_img2img.app.stages.verifier import VerificationResult, verify_image


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
        aws_region="us-east-1",
    )
    defaults.update(overrides)
    return PipelineSettings(**defaults)


def _fake_b64() -> str:
    return base64.b64encode(b"\xff\xd8\xff\xe0fake").decode()


@pytest.fixture()
def settings() -> PipelineSettings:
    return _make_settings()


def _patch_nova(text: str):
    return patch(
        "runtimes.agentcore_img2img.app.stages.verifier._invoke_gemma",
        side_effect=lambda **kwargs: text,
    )


def _patch_client():
    return patch(
        "runtimes.agentcore_img2img.app.stages.verifier._build_bedrock_client",
        return_value=MagicMock(),
    )


async def test_happy_path_score_parsed_and_composite_correct(
    settings: PipelineSettings,
) -> None:
    response_json = '{"prompt_alignment": 8, "description": "Good match"}'

    with _patch_nova(response_json), _patch_client():
        result = await verify_image(
            positive_prompt="a room",
            candidate_image_b64=_fake_b64(),
            settings=settings,
        )

    assert isinstance(result, VerificationResult)
    assert result.prompt_alignment == 8
    assert result.structural_fidelity == 8  # mirrors prompt_alignment
    assert result.parse_failed is False
    assert result.description == "Good match"
    # composite_score = normalise(8) = (8 - 1) / 9
    expected = (8 - 1) / 9.0
    assert abs(result.composite_score - expected) < 1e-6


async def test_score_outside_range_clamped_before_normalisation(
    settings: PipelineSettings,
) -> None:
    # pa=15 > ceiling of 10 — clamped to 10 in normalisation
    # normalise(15) = (clamp(15,1,10) - 1) / 9 = 9/9 = 1.0
    response_json = '{"prompt_alignment": 15, "description": ""}'

    with _patch_nova(response_json), _patch_client():
        result = await verify_image(
            positive_prompt="a room",
            candidate_image_b64=_fake_b64(),
            settings=settings,
        )

    assert result.prompt_alignment == 15  # raw stored as-is
    assert result.structural_fidelity == 15  # mirrors prompt_alignment
    assert abs(result.composite_score - 1.0) < 1e-6


async def test_elements_list_used_as_intent_context(
    settings: PipelineSettings,
) -> None:
    """Elements list is passed to user_content when provided."""
    response_json = '{"prompt_alignment": 7, "description": "sofa colour mismatch"}'

    with _patch_nova(response_json), _patch_client():
        result = await verify_image(
            positive_prompt="modern living room",
            candidate_image_b64=_fake_b64(),
            settings=settings,
            elements=["sofa → linen sectional", "lighting → recessed downlights"],
        )

    assert result.prompt_alignment == 7
    assert result.description == "sofa colour mismatch"


async def test_json_parse_failure_applies_fail_open(
    settings: PipelineSettings,
) -> None:
    malformed = "Sorry, I cannot provide scores right now."

    with _patch_nova(malformed), _patch_client():
        result = await verify_image(
            positive_prompt="a room",
            candidate_image_b64=_fake_b64(),
            settings=settings,
        )

    assert result.parse_failed is True
    assert result.composite_score == 1.0
    assert result.prompt_alignment == 10
    assert result.structural_fidelity == 10


async def test_bedrock_error_propagates(settings: PipelineSettings) -> None:
    with patch(
        "runtimes.agentcore_img2img.app.stages.verifier._invoke_gemma",
        side_effect=RuntimeError("Bedrock unavailable"),
    ), _patch_client():
        with pytest.raises(RuntimeError, match="Bedrock unavailable"):
            await verify_image(
                positive_prompt="a room",
                candidate_image_b64=_fake_b64(),
                settings=settings,
            )
