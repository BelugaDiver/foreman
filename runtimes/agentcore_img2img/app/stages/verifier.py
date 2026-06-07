from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass

import boto3

from runtimes.agentcore_img2img.app.stages.rewriter import _build_bedrock_client, _invoke_nova

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTION = (
    "You are an expert image quality evaluator. "
    "You will be shown two images (a reference image and a generated candidate image) "
    "and the original prompt that was used to guide the generation. "
    "Evaluate the candidate image on two axes:\n"
    "  1. prompt_alignment: how well the candidate matches the text prompt (1=no match, 10=perfect)\n"
    "  2. structural_fidelity: how well the candidate preserves the spatial composition and "
    "structural elements of the reference image (1=completely different, 10=identical structure)\n"
    "Respond ONLY with valid JSON — no preamble, no explanation, no markdown fences.\n"
    'Required schema: {"prompt_alignment": <integer 1-10>, '
    '"structural_fidelity": <integer 1-10>, "description": "<one sentence>"}'
)


@dataclass
class VerificationResult:
    """Output of Stage 3 dual-axis verification.

    Attributes:
        prompt_alignment: Raw sub-score 1–10 (prompt text alignment).
        structural_fidelity: Raw sub-score 1–10 (structural/spatial fidelity).
        composite_score: 50/50 average of both sub-scores normalised to [0, 1].
        description: Human-readable alignment explanation from the model.
        model_id: Bedrock model ID used (for telemetry).
        latency_ms: Wall-clock milliseconds for the Bedrock call.
        parse_failed: True when JSON parse failed and fail-open was applied (composite=1.0).
    """

    prompt_alignment: int
    structural_fidelity: int
    composite_score: float
    description: str
    model_id: str
    latency_ms: int
    parse_failed: bool


def _clamp(value: int, lo: int = 1, hi: int = 10) -> int:
    return max(lo, min(hi, value))


def _normalise(raw: int) -> float:
    """Normalise a 1–10 score to [0, 1]."""
    return (_clamp(raw) - 1) / 9.0


def _composite(pa: int, sf: int) -> float:
    return (_normalise(pa) + _normalise(sf)) / 2.0


def _parse_scores(text: str) -> tuple[int, int, str] | None:
    """Try to extract (prompt_alignment, structural_fidelity, description) from model output.

    Attempts three strategies in order:
    1. Direct JSON parse of the full text.
    2. Regex extract of the first ``{...}`` block.
    3. Returns None (caller applies fail-open).
    """
    # Strategy 1: direct parse
    try:
        data = json.loads(text)
        pa = int(data["prompt_alignment"])
        sf = int(data["structural_fidelity"])
        desc = str(data.get("description", ""))
        return pa, sf, desc
    except Exception:
        pass

    # Strategy 2: regex extract first JSON object
    match = re.search(r"\{[^}]+\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            pa = int(data["prompt_alignment"])
            sf = int(data["structural_fidelity"])
            desc = str(data.get("description", ""))
            return pa, sf, desc
        except Exception:
            pass

    return None


async def verify_image(
    original_prompt: str,
    reference_image_b64: str,
    candidate_image_b64: str,
    settings,  # PipelineSettings — avoid circular import by using duck typing
    correction_context_max_tokens: int | None = None,
) -> VerificationResult:
    """Invoke Stage 3: dual-axis verification of a candidate generated image.

    Args:
        original_prompt: The user's original text prompt.
        reference_image_b64: Base64-encoded reference (input) image.
        candidate_image_b64: Base64-encoded candidate (generated) image.
        settings: Pipeline configuration (PipelineSettings instance).
        correction_context_max_tokens: Unused; kept for API symmetry.

    Returns:
        VerificationResult. On JSON parse failure, fail-open with composite_score=1.0
        and parse_failed=True.

    Raises:
        Exception: Any Bedrock or network error is propagated to the caller.
    """
    client = _build_bedrock_client(settings.aws_region)

    user_content: list[dict] = [
        {
            "image": {
                "format": "jpeg",
                "source": {"bytes": reference_image_b64},
            }
        },
        {
            "image": {
                "format": "jpeg",
                "source": {"bytes": candidate_image_b64},
            }
        },
        {
            "text": (
                f"Original prompt: {original_prompt}\n\n"
                "The first image is the reference. The second image is the generated candidate. "
                "Evaluate and return scores as specified."
            )
        },
    ]

    start = time.monotonic()
    raw_output: str = await asyncio.to_thread(
        _invoke_nova,
        client=client,
        model_id=settings.prompt_rewrite_model_id,
        system_text=_SYSTEM_INSTRUCTION,
        user_message_content=user_content,
        max_tokens=256,
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    parsed = _parse_scores(raw_output)

    if parsed is None:
        logger.warning(
            "Verification score parse failed; applying fail-open. model_id=%s raw=%r",
            settings.prompt_rewrite_model_id,
            raw_output[:200],
        )
        return VerificationResult(
            prompt_alignment=10,
            structural_fidelity=10,
            composite_score=1.0,
            description="",
            model_id=settings.prompt_rewrite_model_id,
            latency_ms=latency_ms,
            parse_failed=True,
        )

    pa, sf, description = parsed

    # Handle case where one sub-score is missing/zero by substituting the other
    if pa <= 0 and sf > 0:
        pa = sf
    elif sf <= 0 and pa > 0:
        sf = pa

    return VerificationResult(
        prompt_alignment=pa,
        structural_fidelity=sf,
        composite_score=_composite(pa, sf),
        description=description,
        model_id=settings.prompt_rewrite_model_id,
        latency_ms=latency_ms,
        parse_failed=False,
    )
