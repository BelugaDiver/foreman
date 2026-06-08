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


async def test_happy_path_both_scores_parsed_and_composite_correct(
    settings: PipelineSettings,
) -> None:
    response_json = '{"prompt_alignment": 8, "structural_fidelity": 6, "description": "Good match"}'

    with _patch_nova(response_json), _patch_client():
        result = await verify_image(
            original_prompt="a room",
            reference_image_b64=_fake_b64(),
            candidate_image_b64=_fake_b64(),
            settings=settings,
        )

    assert isinstance(result, VerificationResult)
    assert result.prompt_alignment == 8
    assert result.structural_fidelity == 6
    assert result.parse_failed is False
    assert result.description == "Good match"
    # normalise(8) = 7/9 ≈ 0.778, normalise(6) = 5/9 ≈ 0.556, composite = (0.778+0.556)/2 ≈ 0.667
    expected = ((8 - 1) / 9.0 + (6 - 1) / 9.0) / 2.0
    assert abs(result.composite_score - expected) < 1e-6


async def test_score_outside_range_clamped_before_normalisation(
    settings: PipelineSettings,
) -> None:
    # Both scores > 0 but above the 10-point ceiling — should be clamped to 10 in normalisation
    # normalise(15) = (clamp(15,1,10)-1)/9 = 9/9 = 1.0
    # normalise(12) = (clamp(12,1,10)-1)/9 = 9/9 = 1.0
    # composite = (1.0 + 1.0) / 2 = 1.0
    response_json = '{"prompt_alignment": 15, "structural_fidelity": 12, "description": ""}'

    with _patch_nova(response_json), _patch_client():
        result = await verify_image(
            original_prompt="a room",
            reference_image_b64=_fake_b64(),
            candidate_image_b64=_fake_b64(),
            settings=settings,
        )

    assert result.prompt_alignment == 15  # raw stored as-is
    assert result.structural_fidelity == 12
    assert abs(result.composite_score - 1.0) < 1e-6


async def test_one_sub_score_absent_substituted_with_present_score(
    settings: PipelineSettings,
) -> None:
    # structural_fidelity = 0 → should be substituted with prompt_alignment
    response_json = '{"prompt_alignment": 7, "structural_fidelity": 0, "description": "partial"}'

    with _patch_nova(response_json), _patch_client():
        result = await verify_image(
            original_prompt="a room",
            reference_image_b64=_fake_b64(),
            candidate_image_b64=_fake_b64(),
            settings=settings,
        )

    # Both should equal 7 after substitution
    assert result.structural_fidelity == 7
    assert result.prompt_alignment == 7
    expected = ((7 - 1) / 9.0 + (7 - 1) / 9.0) / 2.0
    assert abs(result.composite_score - expected) < 1e-6


async def test_json_parse_failure_applies_fail_open(
    settings: PipelineSettings,
) -> None:
    malformed = "Sorry, I cannot provide scores right now."

    with _patch_nova(malformed), _patch_client():
        result = await verify_image(
            original_prompt="a room",
            reference_image_b64=_fake_b64(),
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
                original_prompt="a room",
                reference_image_b64=_fake_b64(),
                candidate_image_b64=_fake_b64(),
                settings=settings,
            )
