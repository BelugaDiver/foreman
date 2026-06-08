from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass

import boto3

from .rewriter import _build_bedrock_client, _invoke_gemma  # works in ZIP (stages pkg) and dev

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTION = """\
You are an expert interior design quality evaluator.

You will be shown a generated image of a redesigned room, together with the \
design intent that guided its generation.

Evaluate how well the generated image realises the design intent on a scale of \
1 to 10 (1 = completely misses the intent, 10 = perfectly realises it).

Also write one concise sentence identifying the most significant gap between \
the design intent and what is actually visible in the image. This sentence \
will be used to improve the next generation attempt — be specific about what \
is wrong or missing.

Respond ONLY with valid JSON — no markdown fences, no explanation.
Required schema: {"prompt_alignment": <integer 1-10>, "description": "<one sentence describing the main gap>"}
"""


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


def _parse_scores(text: str) -> tuple[int, str] | None:
    """Try to extract (prompt_alignment, description) from model output.

    Attempts three strategies in order:
    1. Direct JSON parse of the full text.
    2. Regex extract of the first ``{...}`` block.
    3. Returns None (caller applies fail-open).
    """
    # Strategy 1: direct parse
    try:
        data = json.loads(text)
        pa = int(data["prompt_alignment"])
        desc = str(data.get("description", ""))
        return pa, desc
    except Exception:
        pass

    # Strategy 2: regex extract first JSON object
    match = re.search(r"\{[^}]+\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            pa = int(data["prompt_alignment"])
            desc = str(data.get("description", ""))
            return pa, desc
        except Exception:
            pass

    return None


async def verify_image(
    positive_prompt: str,
    candidate_image_b64: str,
    settings,  # PipelineSettings — avoid circular import by using duck typing
    elements: list[str] | None = None,
) -> VerificationResult:
    """Invoke Stage V: single-axis verification of the candidate generated image.

    Scores prompt_alignment only (structural fidelity is enforced by ControlNet).
    The ``description`` field contains a correction hint for the next Stage 1 call.

    Args:
        positive_prompt: The positive prompt used to generate the candidate.
        candidate_image_b64: Base64-encoded candidate (generated) image.
        settings: Pipeline configuration (PipelineSettings instance).
        elements: Optional surgical element list from Stage 1 (used as richer context).

    Returns:
        VerificationResult. On JSON parse failure, fail-open with composite_score=1.0
        and parse_failed=True.

    Raises:
        Exception: Any Bedrock or network error is propagated to the caller.
    """
    client = _build_bedrock_client(settings.aws_region)

    if elements:
        intent_text = "Intended changes:\n" + "\n".join(f"- {e}" for e in elements)
    else:
        intent_text = f"Design intent: {positive_prompt}"

    user_content: list[dict] = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{candidate_image_b64}"},
        },
        {
            "type": "text",
            "text": f"{intent_text}\n\nEvaluate this generated image against the design intent.",
        },
    ]

    start = time.monotonic()
    raw_output: str = await asyncio.to_thread(
        _invoke_gemma,
        client=client,
        model_id=settings.prompt_rewrite_model_id,
        system_text=_SYSTEM_INSTRUCTION,
        user_message_content=user_content,
        max_tokens=128,
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

    pa, description = parsed

    return VerificationResult(
        prompt_alignment=pa,
        structural_fidelity=pa,  # single-axis: structural fidelity enforced by ControlNet
        composite_score=_normalise(pa),
        description=description,
        model_id=settings.prompt_rewrite_model_id,
        latency_ms=latency_ms,
        parse_failed=False,
    )
