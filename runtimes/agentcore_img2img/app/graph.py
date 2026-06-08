from __future__ import annotations

import asyncio
import base64
import io
import logging
from urllib.parse import urlparse

import httpx
from opentelemetry import trace
from PIL import Image

try:
    from settings import PipelineSettings  # ZIP deployment (flat root)
    from stages.generator import GenerationResult, generate_image
    from stages.rewriter import RewriteResult, rewrite_prompt
except ImportError:
    from runtimes.agentcore_img2img.app.settings import PipelineSettings  # dev/test
    from runtimes.agentcore_img2img.app.stages.generator import GenerationResult, generate_image
    from runtimes.agentcore_img2img.app.stages.rewriter import RewriteResult, rewrite_prompt

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_CONTENT_TYPE_FORMATS: dict[str, str] = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

_EXT_FORMATS: dict[str, str] = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".webp": "webp",
    ".gif": "gif",
}

_MAX_IMAGE_SIDE = 512  # px — keeps base64 payload well under body size limit


def _fetch_image(url: str) -> tuple[bytes, str]:
    response = httpx.get(url, follow_redirects=True, timeout=10.0)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    fmt = _CONTENT_TYPE_FORMATS.get(content_type)
    if not fmt:
        path = urlparse(url).path.lower()
        for ext, f in _EXT_FORMATS.items():
            if path.endswith(ext):
                fmt = f
                break
    return (response.content, fmt or "jpeg")


def _resize_image(image_bytes: bytes, image_format: str) -> tuple[bytes, str]:
    with Image.open(io.BytesIO(image_bytes)) as img:
        img.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "jpeg"


def _encode_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


async def run_graph(
    *,
    generation_id: str,
    prompt: str,
    input_image_url: str | None,
    style_id: str | None,
) -> dict[str, str | None]:
    """Run the 2-stage img2img pipeline: prompt rewrite → SD ControlNet generation.

    Args:
        generation_id: Unique ID for this invocation (used in telemetry).
        prompt: The user's original text prompt.
        input_image_url: URL to the control/reference image. Required.
        style_id: Optional style hint (unused by model calls, reserved for future use).

    Returns:
        Dict with keys: ``output_image_url``, ``generated_image_description``,
        ``model_used``, ``output_image_bytes``.

    Raises:
        ValueError: If ``input_image_url`` is missing or the URL returns a non-image.
    """
    settings = PipelineSettings.from_env()

    if not input_image_url:
        raise ValueError("input_image_url is required; include a valid image URL in the request.")

    # ── Fetch + resize input image ────────────────────────────────────────────
    with tracer.start_as_current_span("fetch_input_image") as span:
        span.set_attribute("generation_id", generation_id)
        raw_image_bytes, image_format = await asyncio.to_thread(_fetch_image, input_image_url)

    try:
        Image.open(io.BytesIO(raw_image_bytes)).verify()
    except Exception as exc:
        raise ValueError(f"input_image_url does not point to a valid image: {exc}") from exc

    resized_bytes, image_format = _resize_image(raw_image_bytes, image_format)
    image_b64 = _encode_b64(resized_bytes)

    # ── Stage 1: Prompt Rewriting ─────────────────────────────────────────────
    with tracer.start_as_current_span("stage1.rewrite_prompt") as span:
        span.set_attribute("generation_id", generation_id)
        span.set_attribute("model_id", settings.prompt_rewrite_model_id)
        rewrite_result: RewriteResult = await rewrite_prompt(
            original_prompt=prompt,
            image_b64=image_b64,
            image_format=image_format,
            settings=settings,
        )
        logger.info(
            "Stage 1 complete. model_id=%s latency_ms=%d",
            rewrite_result.model_id,
            rewrite_result.latency_ms,
        )

    # ── Stage 2: SD ControlNet Generation ────────────────────────────────────
    with tracer.start_as_current_span("stage2.generate_image") as span:
        span.set_attribute("generation_id", generation_id)
        span.set_attribute("model_id", settings.sd_model_id)
        gen_result: GenerationResult = await generate_image(
            enriched_prompt=rewrite_result.enriched_prompt,
            control_image_bytes=resized_bytes,
            control_image_format=image_format,
            settings=settings,
        )
        logger.info(
            "Stage 2 complete. model_id=%s latency_ms=%d finish_reason=%r has_image=%s",
            gen_result.model_id,
            gen_result.latency_ms,
            gen_result.finish_reason,
            bool(gen_result.image_bytes),
        )

    output_image_bytes: str | None = gen_result.image_b64 if gen_result.image_bytes else None

    if not output_image_bytes:
        logger.warning(
            "Stage 2 produced no image (finish_reason=%r). Returning null bytes.",
            gen_result.finish_reason,
        )

    return {
        "output_image_url": None,
        "generated_image_description": rewrite_result.enriched_prompt,
        "model_used": settings.prompt_rewrite_model_id,
        "output_image_bytes": output_image_bytes,
    }


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_CONTENT_TYPE_FORMATS: dict[str, str] = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

_EXT_FORMATS: dict[str, str] = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".webp": "webp",
    ".gif": "gif",
}

_MAX_IMAGE_SIDE = 512  # px — keeps base64 payload well under body size limit


def _fetch_image(url: str) -> tuple[bytes, str]:
    """Fetch image bytes and format from URL.

    Returns:
        Tuple of (raw bytes, format string).

    Raises:
        ValueError: On HTTP error or unrecognisable content type.
    """
    response = httpx.get(url, follow_redirects=True, timeout=10.0)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    fmt = _CONTENT_TYPE_FORMATS.get(content_type)
    if not fmt:
        path = urlparse(url).path.lower()
        for ext, f in _EXT_FORMATS.items():
            if path.endswith(ext):
                fmt = f
                break
    return (response.content, fmt or "jpeg")


def _resize_image(image_bytes: bytes, image_format: str) -> tuple[bytes, str]:
    """Downscale image so neither side exceeds _MAX_IMAGE_SIDE, re-encode as JPEG."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        img.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "jpeg"


def _encode_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")

