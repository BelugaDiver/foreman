from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import boto3

try:
    from settings import PipelineSettings  # ZIP deployment
except ImportError:
    from runtimes.agentcore_img2img.app.settings import PipelineSettings  # dev/test

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTION = (
    "You are an expert interior design prompt engineer for Stable Diffusion. "
    "The user will give you a short instruction and a photo of a room. "
    "Your job is to produce a single detailed text prompt that will guide a Stable Diffusion ControlNet model "
    "to redesign the room according to the instruction while preserving its structural layout. "
    "Rules: "
    "1. Describe the redesigned room as if it already exists — present tense, photorealistic. "
    "2. Include: lighting conditions, materials (flooring, walls, fabrics), furniture style, colour palette, "
    "   decorative objects, and atmosphere. "
    "3. Do NOT describe what to remove — only describe what the finished room looks like. "
    "4. Do NOT include the word 'realistic' or photographic meta-language like 'shot with'. "
    "5. Output ONLY the prompt text — no preamble, no bullets, no explanation."
)


@dataclass
class RewriteResult:
    """Output of Stage 1 prompt rewriting.

    Attributes:
        enriched_prompt: The full rewritten prompt for SD (never empty).
        model_id: Bedrock model ID used (for telemetry).
        latency_ms: Wall-clock milliseconds for the Bedrock call.
    """

    enriched_prompt: str
    model_id: str
    latency_ms: int


def _build_bedrock_client(region: str) -> object:
    return boto3.client("bedrock-runtime", region_name=region)


def _invoke_gemma(
    *,
    client: object,
    model_id: str,
    system_text: str,
    user_message_content: list[dict],
    max_tokens: int = 512,
) -> str:
    """Synchronous Bedrock invoke_model call using the OpenAI Chat Completions format (Gemma)."""
    body = {
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_message_content},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    resp = client.invoke_model(  # type: ignore[attr-defined]
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(resp["body"].read())
    return result["choices"][0]["message"]["content"].strip()


async def rewrite_prompt(
    original_prompt: str,
    image_b64: str,
    image_format: str,
    settings: PipelineSettings,
    correction_context: str | None = None,
) -> RewriteResult:
    """Invoke Stage 1: rewrite ``original_prompt`` enriched with image context.

    Args:
        original_prompt: The user's original text prompt.
        image_b64: Base64-encoded reference image bytes.
        image_format: Image format string (e.g. ``"jpeg"``).
        settings: Pipeline configuration.
        correction_context: Optional alignment description from the previous
            verification step; appended to the user message to guide refinement.

    Returns:
        RewriteResult with enriched_prompt, model_id, and latency_ms.

    Raises:
        Exception: Any Bedrock or network error is propagated to the caller.
    """
    client = _build_bedrock_client(settings.aws_region)

    user_content: list[dict] = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/{image_format};base64,{image_b64}"},
        },
        {"type": "text", "text": f"Original prompt: {original_prompt}"},
    ]

    if correction_context:
        trimmed = correction_context[: settings.correction_context_max_tokens]
        user_content.append(
            {
                "type": "text",
                "text": f"Previous attempt feedback (use this to improve the prompt): {trimmed}",
            }
        )

    start = time.monotonic()
    raw_output: str = await asyncio.to_thread(
        _invoke_gemma,
        client=client,
        model_id=settings.prompt_rewrite_model_id,
        system_text=_SYSTEM_INSTRUCTION,
        user_message_content=user_content,
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    enriched = raw_output.strip()
    if not enriched:
        logger.warning(
            "Stage 1 returned empty output; substituting original prompt. model_id=%s",
            settings.prompt_rewrite_model_id,
        )
        enriched = original_prompt

    # Enforce prompt length ceiling
    if len(enriched) > settings.sd_prompt_max_tokens:
        enriched = enriched[: settings.sd_prompt_max_tokens]

    return RewriteResult(
        enriched_prompt=enriched,
        model_id=settings.prompt_rewrite_model_id,
        latency_ms=latency_ms,
    )
