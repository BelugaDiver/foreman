from __future__ import annotations

import logging

import pytest

from runtimes.agentcore_img2img.app.settings import (
    _DEFAULT_PROMPT_REWRITE_MODEL_ID,
    _DEFAULT_SD_MODEL_ID,
    _SD_EDGE_MODEL_ID,
    PipelineSettings,
)


def test_defaults_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in [
        "PROMPT_REWRITE_MODEL_ID",
        "SD_MODEL_ID",
        "CONTROLNET_MODE",
        "VERIFICATION_ALIGNMENT_THRESHOLD",
        "VERIFICATION_MAX_ITERATIONS",
        "VERIFICATION_TIME_BUDGET_SECONDS",
        "VERIFICATION_ITER_ESTIMATE_SECONDS",
        "MAX_OUTPUT_IMAGE_BYTES",
        "SD_PROMPT_MAX_TOKENS",
        "CORRECTION_CONTEXT_MAX_TOKENS",
        "AWS_DEFAULT_REGION",
    ]:
        monkeypatch.delenv(var, raising=False)

    s = PipelineSettings.from_env()

    assert s.prompt_rewrite_model_id == _DEFAULT_PROMPT_REWRITE_MODEL_ID
    assert s.sd_model_id == _DEFAULT_SD_MODEL_ID
    assert s.controlnet_mode == "depth"
    assert s.verification_alignment_threshold == 0.75
    assert s.verification_max_iterations == 2
    assert s.verification_time_budget_seconds == 60.0
    assert s.verification_iter_estimate_seconds == 30.0
    assert s.max_output_image_bytes == 1 * 1024 * 1024
    assert s.sd_prompt_max_tokens == 500
    assert s.correction_context_max_tokens == 300
    assert s.aws_region == "us-east-1"


def test_overrides_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPT_REWRITE_MODEL_ID", "amazon.nova-pro-v1:0")
    monkeypatch.setenv("SD_MODEL_ID", "us.stability.custom-v1:0")
    monkeypatch.setenv("CONTROLNET_MODE", "edge")
    monkeypatch.setenv("VERIFICATION_ALIGNMENT_THRESHOLD", "0.85")
    monkeypatch.setenv("VERIFICATION_MAX_ITERATIONS", "5")
    monkeypatch.setenv("VERIFICATION_TIME_BUDGET_SECONDS", "200.0")
    monkeypatch.setenv("VERIFICATION_ITER_ESTIMATE_SECONDS", "40.0")
    monkeypatch.setenv("MAX_OUTPUT_IMAGE_BYTES", "2097152")
    monkeypatch.setenv("SD_PROMPT_MAX_TOKENS", "800")
    monkeypatch.setenv("CORRECTION_CONTEXT_MAX_TOKENS", "400")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")

    s = PipelineSettings.from_env()

    assert s.prompt_rewrite_model_id == "amazon.nova-pro-v1:0"
    # SD_MODEL_ID explicitly set — should win over controlnet_mode default
    assert s.sd_model_id == "us.stability.custom-v1:0"
    assert s.controlnet_mode == "edge"
    assert s.verification_alignment_threshold == 0.85
    assert s.verification_max_iterations == 5
    assert s.verification_time_budget_seconds == 200.0
    assert s.verification_iter_estimate_seconds == 40.0
    assert s.max_output_image_bytes == 2097152
    assert s.sd_prompt_max_tokens == 800
    assert s.correction_context_max_tokens == 400
    assert s.aws_region == "eu-west-1"


def test_edge_mode_selects_sketch_model_when_sd_model_id_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONTROLNET_MODE", "edge")
    monkeypatch.delenv("SD_MODEL_ID", raising=False)

    s = PipelineSettings.from_env()

    assert s.sd_model_id == _SD_EDGE_MODEL_ID
    assert s.controlnet_mode == "edge"


def test_depth_mode_selects_structure_model_when_sd_model_id_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONTROLNET_MODE", "depth")
    monkeypatch.delenv("SD_MODEL_ID", raising=False)

    s = PipelineSettings.from_env()

    assert s.sd_model_id == _DEFAULT_SD_MODEL_ID


def test_unsupported_controlnet_mode_falls_back_to_depth_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("CONTROLNET_MODE", "sketch")
    monkeypatch.delenv("SD_MODEL_ID", raising=False)

    with caplog.at_level(logging.WARNING, logger="runtimes.agentcore_img2img.app.settings"):
        s = PipelineSettings.from_env()

    assert s.controlnet_mode == "depth"
    assert s.sd_model_id == _DEFAULT_SD_MODEL_ID
    assert any("CONTROLNET_MODE" in msg for msg in caplog.messages)
