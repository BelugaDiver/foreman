from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Default model identifiers
_DEFAULT_PROMPT_REWRITE_MODEL_ID = "amazon.nova-lite-v1:0"
_DEFAULT_SD_MODEL_ID = "us.stability.stable-image-control-structure-v1:0"
_SD_EDGE_MODEL_ID = "us.stability.stable-image-control-sketch-v1:0"

_SUPPORTED_CONTROLNET_MODES = {"depth", "edge"}


class PipelineSettings:
    """All runtime configuration loaded from environment variables.

    Attributes:
        prompt_rewrite_model_id: Bedrock model ID for Stage 1 (prompt rewriting and verification).
        sd_model_id: Bedrock model ID for Stage 2 (Stable Diffusion ControlNet generation).
        controlnet_mode: ControlNet conditioning mode — ``depth`` or ``edge``.
        verification_alignment_threshold: Composite score (0–1) required to exit loop early.
        verification_max_iterations: Hard cap on verification loop iterations.
        verification_time_budget_seconds: Wall-clock budget for the entire loop.
        verification_iter_estimate_seconds: Estimated seconds per SD + verify round-trip.
        max_output_image_bytes: Ceiling for base64-decoded output image size in bytes.
        sd_prompt_max_tokens: Character limit for the enriched prompt passed to SD.
        correction_context_max_tokens: Character limit for correction context fed back to Stage 1.
        output_base_url: Base URL prefix used to construct ``output_image_url`` in the response.
        aws_region: AWS region for Bedrock client.
    """

    def __init__(
        self,
        *,
        prompt_rewrite_model_id: str,
        sd_model_id: str,
        controlnet_mode: str,
        verification_alignment_threshold: float,
        verification_max_iterations: int,
        verification_time_budget_seconds: float,
        verification_iter_estimate_seconds: float,
        max_output_image_bytes: int,
        sd_prompt_max_tokens: int,
        correction_context_max_tokens: int,
        output_base_url: str,
        aws_region: str,
    ) -> None:
        self.prompt_rewrite_model_id = prompt_rewrite_model_id
        self.sd_model_id = sd_model_id
        self.controlnet_mode = controlnet_mode
        self.verification_alignment_threshold = verification_alignment_threshold
        self.verification_max_iterations = verification_max_iterations
        self.verification_time_budget_seconds = verification_time_budget_seconds
        self.verification_iter_estimate_seconds = verification_iter_estimate_seconds
        self.max_output_image_bytes = max_output_image_bytes
        self.sd_prompt_max_tokens = sd_prompt_max_tokens
        self.correction_context_max_tokens = correction_context_max_tokens
        self.output_base_url = output_base_url.rstrip("/")
        self.aws_region = aws_region

    @classmethod
    def from_env(cls) -> "PipelineSettings":
        """Construct settings from environment variables, logging warnings for missing values."""
        output_base_url = os.getenv("RUNTIME_OUTPUT_BASE_URL", "").strip()
        if not output_base_url:
            logger.warning(
                "RUNTIME_OUTPUT_BASE_URL is not set; output_image_url will be invalid"
            )

        controlnet_mode = os.getenv("CONTROLNET_MODE", "depth").strip().lower()
        if controlnet_mode not in _SUPPORTED_CONTROLNET_MODES:
            logger.warning(
                "Unsupported CONTROLNET_MODE %r — falling back to 'depth'", controlnet_mode
            )
            controlnet_mode = "depth"

        sd_model_id = os.getenv("SD_MODEL_ID", "").strip()
        if not sd_model_id:
            sd_model_id = (
                _SD_EDGE_MODEL_ID if controlnet_mode == "edge" else _DEFAULT_SD_MODEL_ID
            )

        return cls(
            prompt_rewrite_model_id=os.getenv(
                "PROMPT_REWRITE_MODEL_ID", _DEFAULT_PROMPT_REWRITE_MODEL_ID
            ).strip(),
            sd_model_id=sd_model_id,
            controlnet_mode=controlnet_mode,
            verification_alignment_threshold=float(
                os.getenv("VERIFICATION_ALIGNMENT_THRESHOLD", "0.75")
            ),
            verification_max_iterations=int(
                os.getenv("VERIFICATION_MAX_ITERATIONS", "3")
            ),
            verification_time_budget_seconds=float(
                os.getenv("VERIFICATION_TIME_BUDGET_SECONDS", "120.0")
            ),
            verification_iter_estimate_seconds=float(
                os.getenv("VERIFICATION_ITER_ESTIMATE_SECONDS", "30.0")
            ),
            max_output_image_bytes=int(
                os.getenv("MAX_OUTPUT_IMAGE_BYTES", str(1 * 1024 * 1024))
            ),
            sd_prompt_max_tokens=int(os.getenv("SD_PROMPT_MAX_TOKENS", "500")),
            correction_context_max_tokens=int(
                os.getenv("CORRECTION_CONTEXT_MAX_TOKENS", "300")
            ),
            output_base_url=output_base_url,
            aws_region=os.getenv("AWS_DEFAULT_REGION", "us-east-1").strip(),
        )
