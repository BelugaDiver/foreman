from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import boto3

from runtimes.agentcore_img2img.app.settings import PipelineSettings

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTION = (
    "You are an expert image-generation prompt engineer. "
    "Your task is to rewrite the user's prompt into a detailed, vivid description "
    "suitable for a Stable Diffusion model. "
    "Incorporate visual details you observe in the attached reference image. "
    "Output ONLY the rewritten prompt — no preamble, no explanation, no markdown. "
    "The rewritten prompt MUST be at least as long as the original prompt. "
    "If the original prompt is already detailed, enrich it further. "
    "If you cannot produce a meaningful rewrite, reproduce the original prompt verbatim."
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


def _invoke_nova(
    *,
    client: object,
    model_id: str,
    system_text: str,
    user_message_content: list[dict],
    max_tokens: int = 512,
) -> str:
    """Synchronous Bedrock invoke_model call using the Nova messages-v1 schema."""
    body = {
        "schemaVersion": "messages-v1",
        "system": [{"text": system_text}],
        "messages": [{"role": "user", "content": user_message_content}],
        "inferenceConfig": {"max_new_tokens": max_tokens, "temperature": 0.7},
    }
    resp = client.invoke_model(  # type: ignore[attr-defined]
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(resp["body"].read())
    return result["output"]["message"]["content"][0]["text"].strip()


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
            "image": {
                "format": image_format,
                "source": {"bytes": image_b64},
            }
        },
        {"text": f"Original prompt: {original_prompt}"},
    ]

    if correction_context:
        trimmed = correction_context[: settings.correction_context_max_tokens]
        user_content.append(
            {
                "text": (
                    f"Previous attempt feedback (use this to improve the prompt): {trimmed}"
                )
            }
        )

    start = time.monotonic()
    raw_output: str = await asyncio.to_thread(
        _invoke_nova,
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
