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

_SYSTEM_INSTRUCTION = """\
You are an expert interior design analyst and Stable Diffusion prompt engineer.
The user will give you a short instruction and a photo of a room.

Your job is to analyse the image, infer the intended interior design style from \
the instruction (even if vague — e.g. "cozy" → Scandinavian hygge, warm \
textiles, soft lighting), and identify exactly which elements of the room should \
change to realise that intent.

Respond ONLY with a JSON object — no markdown fences, no explanation — in this \
exact shape:
{
  "elements": [
    "<element in the image> → <what it becomes>",
    ...
  ],
  "positive_prompt": "<focused SD prompt — see rules below>",
  "negative_prompt": "<comma-separated list of things to avoid>"
}

Rules for "elements":
- List every specific object, surface, or fixture that changes (e.g. \
"sofa → low-profile linen sectional in warm oat", "pendant light → brushed \
brass arc floor lamp").
- NEVER include walls, ceiling height, room layout, or any other load-bearing \
or structural feature unless the user's instruction explicitly and \
unambiguously requests that specific change. When in doubt, leave it out.
- Windows and doors: you MAY change the style, frame finish, glazing, or \
hardware of existing windows and doors if the user's intent calls for it \
(e.g. "industrial" → black steel-framed windows). You must NEVER add, \
remove, or relocate a window or door opening — openings are fixed by the \
building structure and cannot be changed without construction.
- NEVER add a skylight or any new opening that does not already exist in \
the photo. Do not invent light sources by adding architecture.
- If the instruction implies a drastic spatial change (e.g. "open plan", \
"remove the wall"), include a structural note like \
"room layout → open-plan with no dividing wall".

Rules for "positive_prompt" — CRITICAL:
- ONLY describe the elements that are changing. Do NOT describe elements \
that are staying the same. The ControlNet structure model will preserve \
everything unchanged directly from the photo — describing unchanged \
elements forces the model to overwrite them.
- Start with a brief style anchor (e.g. "Scandinavian hygge interior,") \
then list each changing element with its new appearance.
- Use precise interior design vocabulary for each changed element: \
material, finish, colour, form factor (e.g. "low-profile linen sectional \
in warm oat", "brushed brass arc floor lamp with linen shade").
- Do NOT describe flooring, walls, ceiling, lighting quality, or atmosphere \
unless those specific things are explicitly changing per the user's prompt.
- Do NOT add, remove, or relocate any window or door opening. You may \
describe changes to the style, frame, or glazing of windows and doors that \
already exist in the photo if the user's intent calls for it.
- Do NOT add skylights or any new opening not visible in the original photo.
- Do NOT use the word "realistic" or photographic meta-language like \
"shot with" or "DSLR".
- Keep the prompt concise — 30 to 100 words is sufficient.

Rules for "negative_prompt":
- List artefacts, distortions, and stylistic clashes specific to the \
requested style that Stable Diffusion commonly produces.
- Always include: ugly, deformed, blurry, watermark, text, signature.
- Add style-specific exclusions (e.g. for minimalist: ornate, cluttered, \
maximalist; for rustic: chrome, plastic, futuristic).
"""


@dataclass
class RewriteResult:
    """Output of Stage 1 prompt rewriting.

    Attributes:
        positive_prompt: SD positive prompt describing the finished room.
        negative_prompt: SD negative prompt listing things to avoid.
        elements: Surgical list of element-level changes (for telemetry).
        model_id: Bedrock model ID used (for telemetry).
        latency_ms: Wall-clock milliseconds for the Bedrock call.
    """

    positive_prompt: str
    negative_prompt: str
    elements: list[str]
    model_id: str
    latency_ms: int

    @property
    def enriched_prompt(self) -> str:
        """Alias for positive_prompt (backwards compatibility)."""
        return self.positive_prompt


def _build_bedrock_client(region: str) -> object:
    return boto3.client("bedrock-runtime", region_name=region)


def _parse_gemma_json(raw: str, original_prompt: str) -> tuple[str, str, list[str]]:
    """Leniently parse Gemma's JSON output into (positive_prompt, negative_prompt, elements).

    Strips markdown fences if present, then attempts JSON parsing. Falls back to
    using ``raw`` as the positive_prompt when parsing fails.
    """
    text = raw.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
    try:
        data = json.loads(text)
        positive = str(data.get("positive_prompt") or "").strip() or original_prompt
        negative = str(data.get("negative_prompt") or "").strip()
        elements = [str(e) for e in data.get("elements") or []]
        return positive, negative, elements
    except (json.JSONDecodeError, TypeError, AttributeError):
        logger.warning("Stage 1 returned non-JSON output; using raw text as positive_prompt.")
        return raw.strip() or original_prompt, "", []


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

    positive_prompt, negative_prompt, elements = _parse_gemma_json(raw_output, original_prompt)

    if len(positive_prompt) > settings.sd_prompt_max_tokens:
        positive_prompt = positive_prompt[: settings.sd_prompt_max_tokens]

    logger.info(
        "Stage 1 parsed. elements=%d positive_len=%d negative_len=%d",
        len(elements),
        len(positive_prompt),
        len(negative_prompt),
    )

    return RewriteResult(
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        elements=elements,
        model_id=settings.prompt_rewrite_model_id,
        latency_ms=latency_ms,
    )
