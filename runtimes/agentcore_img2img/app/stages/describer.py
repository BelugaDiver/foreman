from __future__ import annotations

import asyncio
import logging
import time

try:
    from settings import PipelineSettings  # ZIP deployment
    from stages.rewriter import RewriteResult, _build_bedrock_client, _invoke_gemma
except ImportError:
    from runtimes.agentcore_img2img.app.settings import PipelineSettings  # dev/test
    from runtimes.agentcore_img2img.app.stages.rewriter import (
        RewriteResult,
        _build_bedrock_client,
        _invoke_gemma,
    )

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTION = """\
You are an expert interior design consultant reviewing a room that has just been \
redesigned by an AI model.

You will receive:
1. A design intent description — what the AI was instructed to produce.
2. The actual generated image of the redesigned room.

Your job is to describe the changes visible in the image as design \
recommendations, using "should" with a bare infinitive for each change \
(e.g. "The sofa should be replaced with a low-profile linen sectional in warm \
oat tones.", "The overhead lighting should be swapped for soft recessed \
downlights.").

Rules:
- Base your description strictly on what is visible in the generated image. \
  Do not invent changes that are not visible.
- Use the design intent description only to understand what was attempted — \
  not as a source of facts about the image.
- Write 2 - 5 paragraphs covering the most significant visible changes.
- Use precise interior design vocabulary.
- Do not mention AI, models, prompts, or the generation process.
- Output markdown formatted content. Be engaging and informative, but be concise.
- DO NOT EVER ADD A PREAMBLE OR AN INTRODUCTORY SENTENCE — start describing the changes immediately.
- USE SENTENCES LIKE, Added a vintage Persian rug to anchor the seating area and introduce warm colors. \
    NOT, The AI added a vintage Persian rug...
- Enter the role of the creator/designer of the redesigned room. \
    Imagine you are describing the changes to a client who is considering implementing them.
- use markdown formatting, including headers, bullet points, \
    and bolding to make the content engaging and easy to read.
"""


async def describe_generation(
    rewrite_result: RewriteResult,
    generated_image_b64: str,
    generated_image_format: str,
    settings: PipelineSettings,
) -> str:
    """Invoke Stage 3: describe the generated image as design recommendations.

    Args:
        rewrite_result: Output from Stage 1, used to provide design intent context.
        generated_image_b64: Base64-encoded generated image bytes.
        generated_image_format: Image format string (e.g. ``"jpeg"``).
        settings: Pipeline configuration.

    Returns:
        A natural-language description of the visible changes framed as
        recommendations. Falls back to the positive_prompt if the call fails.
    """
    client = _build_bedrock_client(settings.aws_region)

    # Build context from rewrite result — elements list if available, else positive_prompt
    if rewrite_result.elements:
        intent_text = "Intended changes:\n" + "\n".join(
            f"- {e}" for e in rewrite_result.elements
        )
    else:
        intent_text = f"Design intent: {rewrite_result.positive_prompt}"

    user_content: list[dict] = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/{generated_image_format};base64,{generated_image_b64}"
            },
        },
        {"type": "text", "text": intent_text},
    ]

    start = time.monotonic()
    try:
        description = await asyncio.to_thread(
            _invoke_gemma,
            client=client,
            model_id=settings.prompt_rewrite_model_id,
            system_text=_SYSTEM_INSTRUCTION,
            user_message_content=user_content,
            max_tokens=256,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.info("Stage 3 complete. latency_ms=%d", latency_ms)
        return description.strip() or rewrite_result.positive_prompt
    except Exception:
        logger.warning("Stage 3 failed; falling back to positive_prompt.", exc_info=True)
        return rewrite_result.positive_prompt
