from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from urllib.parse import urlparse

import httpx
from opentelemetry import trace
from PIL import Image

try:
    from settings import PipelineSettings  # ZIP deployment (flat root)
    from stages.describer import describe_generation
    from stages.generator import GenerationResult, generate_image
    from stages.rewriter import RewriteResult, rewrite_prompt
    from stages.verifier import VerificationResult, verify_image
except ImportError:
    from runtimes.agentcore_img2img.app.settings import PipelineSettings  # dev/test
    from runtimes.agentcore_img2img.app.stages.describer import describe_generation
    from runtimes.agentcore_img2img.app.stages.generator import GenerationResult, generate_image
    from runtimes.agentcore_img2img.app.stages.rewriter import RewriteResult, rewrite_prompt
    from runtimes.agentcore_img2img.app.stages.verifier import VerificationResult, verify_image

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


async def run_graph(
    *,
    generation_id: str,
    prompt: str,
    input_image_url: str | None,
    style_id: str | None,
) -> dict[str, str | None]:
    """Run the img2img pipeline: prompt rewrite → SD ControlNet generation → verify loop → describe.

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

    # ── Stage 1: Initial Prompt Rewriting ─────────────────────────────────────
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

    # ── Verification loop: Stage 2 (generate) + Stage V (verify) ─────────────
    best_gen: GenerationResult | None = None
    best_score: float = -1.0
    best_rewrite: RewriteResult = rewrite_result
    correction_context: str | None = None
    loop_start = time.monotonic()

    for iteration in range(settings.verification_max_iterations):
        # Time budget guard: skip if we can't fit another round-trip
        if iteration > 0:
            elapsed = time.monotonic() - loop_start
            remaining = settings.verification_time_budget_seconds - elapsed
            if remaining < settings.verification_iter_estimate_seconds:
                logger.info(
                    "Verification loop: time budget exhausted before iteration %d", iteration
                )
                break
            # Re-run Stage 1 with correction context from previous verify
            with tracer.start_as_current_span("stage1.rewrite_prompt") as span:
                span.set_attribute("generation_id", generation_id)
                span.set_attribute("iteration", iteration)
                rewrite_result = await rewrite_prompt(
                    original_prompt=prompt,
                    image_b64=image_b64,
                    image_format=image_format,
                    settings=settings,
                    correction_context=correction_context,
                )
                logger.info(
                    "Stage 1 (iter %d) complete. latency_ms=%d",
                    iteration,
                    rewrite_result.latency_ms,
                )

        # Stage 2: generate
        with tracer.start_as_current_span("stage2.generate_image") as span:
            span.set_attribute("generation_id", generation_id)
            span.set_attribute("iteration", iteration)
            span.set_attribute("model_id", settings.sd_model_id)
            gen_result: GenerationResult = await generate_image(
                enriched_prompt=rewrite_result.positive_prompt,
                control_image_bytes=resized_bytes,
                control_image_format=image_format,
                settings=settings,
                **({"negative_prompt": rewrite_result.negative_prompt} if rewrite_result.negative_prompt else {}),
            )
            logger.info(
                "Stage 2 (iter %d) complete. model_id=%s latency_ms=%d finish_reason=%r has_image=%s",
                iteration,
                gen_result.model_id,
                gen_result.latency_ms,
                gen_result.finish_reason,
                bool(gen_result.image_bytes),
            )

        if not gen_result.image_bytes:
            logger.warning("Stage 2 (iter %d) produced no image; skipping verification.", iteration)
            if best_gen is None:
                best_gen = gen_result
                best_rewrite = rewrite_result
            continue

        # Stage V: verify
        with tracer.start_as_current_span("stage_v.verify_image") as span:
            span.set_attribute("generation_id", generation_id)
            span.set_attribute("iteration", iteration)
            verify_result: VerificationResult = await verify_image(
                positive_prompt=rewrite_result.positive_prompt,
                candidate_image_b64=gen_result.image_b64,
                settings=settings,
                elements=rewrite_result.elements or None,
            )
            span.set_attribute("composite_score", verify_result.composite_score)
            logger.info(
                "Stage V (iter %d) score=%.3f description=%r",
                iteration,
                verify_result.composite_score,
                verify_result.description[:100],
            )

        if verify_result.composite_score > best_score:
            best_score = verify_result.composite_score
            best_gen = gen_result
            best_rewrite = rewrite_result

        correction_context = verify_result.description

        if verify_result.composite_score >= settings.verification_alignment_threshold:
            logger.info(
                "Verification loop: threshold met at iteration %d (score=%.3f)",
                iteration,
                verify_result.composite_score,
            )
            break

    output_image_bytes: str | None = (
        best_gen.image_b64 if best_gen and best_gen.image_bytes else None
    )

    if not output_image_bytes:
        logger.warning("All verification iterations produced no image.")

    # ── Stage 3: Generate user-facing description ─────────────────────────────
    if output_image_bytes:
        with tracer.start_as_current_span("stage3.describe_generation") as span:
            span.set_attribute("generation_id", generation_id)
            generated_image_description = await describe_generation(
                rewrite_result=best_rewrite,
                generated_image_b64=output_image_bytes,
                generated_image_format="jpeg",
                settings=settings,
            )
    else:
        generated_image_description = best_rewrite.positive_prompt

    return {
        "output_image_url": None,
        "generated_image_description": generated_image_description,
        "model_used": settings.prompt_rewrite_model_id,
        "output_image_bytes": output_image_bytes,
    }

