from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import time
from urllib.parse import urlparse

import httpx
from opentelemetry import trace
from PIL import Image

from runtimes.agentcore_img2img.app.settings import PipelineSettings
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
    """Run the 3-stage img2img pipeline with a verification loop.

    Stages:
      1. Prompt rewriting (Nova Lite multimodal)
      2. SD ControlNet generation
      3. Verification loop with score-based retry

    Args:
        generation_id: Unique ID for this invocation (used in telemetry + URL).
        prompt: The user's original text prompt.
        input_image_url: URL to the control/reference image. Required.
        style_id: Optional style hint (passed through; unused by model calls).

    Returns:
        Dict matching RuntimeInvocationResponse fields:
        ``output_image_url``, ``generated_image_description``, ``model_used``,
        ``output_image_bytes``.

    Raises:
        ValueError: If ``input_image_url`` is missing or ``RUNTIME_OUTPUT_BASE_URL`` is unset.
        Exception: Stage 1 errors propagate; Stage 2/3 errors are handled gracefully.
    """
    settings = PipelineSettings.from_env()

    output_base_url = settings.output_base_url
    if not output_base_url:
        raise ValueError(
            "RUNTIME_OUTPUT_BASE_URL must be configured; "
            "set the environment variable before invoking the runtime."
        )

    if not input_image_url:
        raise ValueError(
            "input_image_url is required for this runtime; "
            "include a valid image URL in the request."
        )

    # ── Fetch + validate input image ────────────────────────────────────────
    raw_image_bytes, image_format = await asyncio.to_thread(_fetch_image, input_image_url)

    try:
        Image.open(io.BytesIO(raw_image_bytes)).verify()
    except Exception as exc:
        raise ValueError(f"input_image_url does not point to a valid image: {exc}") from exc

    resized_bytes, image_format = _resize_image(raw_image_bytes, image_format)
    image_b64 = _encode_b64(resized_bytes)

    # ── Stage 1: Prompt Rewriting ────────────────────────────────────────────
    with tracer.start_as_current_span("stage1.rewrite_prompt") as span:
        span.set_attribute("generation_id", generation_id)
        span.set_attribute("model_id", settings.prompt_rewrite_model_id)
        stage1_start = time.monotonic()
        rewrite_result: RewriteResult = await rewrite_prompt(
            original_prompt=prompt,
            image_b64=image_b64,
            image_format=image_format,
            settings=settings,
        )
        span.set_attribute("latency_ms", int((time.monotonic() - stage1_start) * 1000))

    enriched_prompt = rewrite_result.enriched_prompt

    # ── Verification Loop ───────────────────────────────────────────────────
    loop_start = time.monotonic()
    iteration = 0
    correction_context: str | None = None

    best_generation: GenerationResult | None = None
    best_verification: VerificationResult | None = None
    best_score: float = -1.0
    exit_reason: str = "max_iterations"

    # Track the last successful description for FR-007 fallback
    last_description: str = enriched_prompt

    while iteration < settings.verification_max_iterations:
        elapsed = time.monotonic() - loop_start
        remaining = settings.verification_time_budget_seconds - elapsed

        if remaining < settings.verification_iter_estimate_seconds:
            exit_reason = "time_budget_precheck"
            logger.info(
                "Verification loop: exiting before iteration %d — time budget insufficient. "
                "remaining=%.1fs estimate=%.1fs",
                iteration,
                remaining,
                settings.verification_iter_estimate_seconds,
            )
            break

        iteration += 1
        logger.info(
            "Verification loop iteration %d / %d",
            iteration,
            settings.verification_max_iterations,
        )

        # ── Stage 2: SD ControlNet Generation ───────────────────────────────
        with tracer.start_as_current_span("stage2.generate_image") as span:
            span.set_attribute("generation_id", generation_id)
            span.set_attribute("model_id", settings.sd_model_id)
            span.set_attribute("iteration", iteration)
            stage2_start = time.monotonic()
            gen_result: GenerationResult = await generate_image(
                enriched_prompt=enriched_prompt,
                control_image_bytes=resized_bytes,
                control_image_format=image_format,
                settings=settings,
            )
            span.set_attribute("latency_ms", int((time.monotonic() - stage2_start) * 1000))
            span.set_attribute("finish_reason", gen_result.finish_reason or "success")

        if not gen_result.image_bytes:
            logger.warning(
                "Stage 2 failed on iteration %d (finish_reason=%r); "
                "continuing to next iteration.",
                iteration,
                gen_result.finish_reason,
            )
            continue

        # ── Stage 3: Verification ────────────────────────────────────────────
        with tracer.start_as_current_span("stage3.verify_image") as span:
            span.set_attribute("generation_id", generation_id)
            span.set_attribute("model_id", settings.prompt_rewrite_model_id)
            span.set_attribute("iteration", iteration)
            stage3_start = time.monotonic()
            ver_result: VerificationResult = await verify_image(
                original_prompt=prompt,
                reference_image_b64=image_b64,
                candidate_image_b64=gen_result.image_b64,
                settings=settings,
            )
            span.set_attribute("latency_ms", int((time.monotonic() - stage3_start) * 1000))
            span.set_attribute("composite_score", ver_result.composite_score)
            span.set_attribute("prompt_alignment", ver_result.prompt_alignment)
            span.set_attribute("structural_fidelity", ver_result.structural_fidelity)
            span.set_attribute("parse_failed", ver_result.parse_failed)

        logger.info(
            "Iteration %d: composite=%.3f prompt_alignment=%d structural_fidelity=%d "
            "parse_failed=%s exit_reason_candidate=%s",
            iteration,
            ver_result.composite_score,
            ver_result.prompt_alignment,
            ver_result.structural_fidelity,
            ver_result.parse_failed,
            "threshold_met" if ver_result.composite_score >= settings.verification_alignment_threshold else "continue",
        )

        # Update best tracking
        if ver_result.composite_score > best_score:
            best_score = ver_result.composite_score
            best_generation = gen_result
            best_verification = ver_result

        if ver_result.description:
            last_description = ver_result.description

        # Fail-open: parse failure → accept current result, exit
        if ver_result.parse_failed:
            exit_reason = "verification_parse_failure"
            logger.info("Verification loop: fail-open exit on iteration %d", iteration)
            break

        # Threshold met → exit early
        if ver_result.composite_score >= settings.verification_alignment_threshold:
            exit_reason = "threshold_met"
            logger.info(
                "Verification loop: threshold met (%.3f >= %.3f) on iteration %d",
                ver_result.composite_score,
                settings.verification_alignment_threshold,
                iteration,
            )
            break

        # Prepare next iteration: use correction context to refine prompt
        correction_context = ver_result.description
        with tracer.start_as_current_span("stage1.rewrite_prompt.refinement") as span:
            span.set_attribute("generation_id", generation_id)
            span.set_attribute("model_id", settings.prompt_rewrite_model_id)
            span.set_attribute("iteration", iteration)
            rewrite_result = await rewrite_prompt(
                original_prompt=prompt,
                image_b64=image_b64,
                image_format=image_format,
                settings=settings,
                correction_context=correction_context,
            )
        enriched_prompt = rewrite_result.enriched_prompt

    # ── Loop exit telemetry ──────────────────────────────────────────────────
    total_ms = int((time.monotonic() - loop_start) * 1000)
    logger.info(
        "Verification loop complete. exit_reason=%s iterations=%d total_ms=%d best_score=%.3f",
        exit_reason,
        iteration,
        total_ms,
        best_score,
    )

    # ── Build response ───────────────────────────────────────────────────────
    output_image_bytes: str | None = None
    if best_generation and best_generation.image_bytes:
        output_image_bytes = best_generation.image_b64

    return {
        "output_image_url": f"{output_base_url}/{generation_id}.jpg",
        "generated_image_description": last_description,
        "model_used": settings.prompt_rewrite_model_id,
        "output_image_bytes": output_image_bytes,
    }
