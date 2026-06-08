from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
from dataclasses import dataclass

import boto3
from PIL import Image

try:
    from settings import PipelineSettings  # ZIP deployment
except ImportError:
    from runtimes.agentcore_img2img.app.settings import PipelineSettings  # dev/test

logger = logging.getLogger(__name__)

_MAX_JPEG_QUALITY = 85
_MIN_JPEG_QUALITY = 40
_MAX_IMAGE_SIDE = 512  # pixels — keeps base64 payload well under Bedrock body limit
_SD_OUTPUT_FORMAT = "jpeg"


@dataclass
class GenerationResult:
    """Output of Stage 2 SD ControlNet generation.

    Attributes:
        image_bytes: Raw decoded JPEG bytes; empty when generation failed.
        image_b64: Base64 string of image_bytes; empty when generation failed.
        finish_reason: Non-null string when SD reports an error/content filter; None on success.
        seed: Seed used by the model (for reproducibility and telemetry).
        model_id: Bedrock model ID used (for telemetry).
        latency_ms: Wall-clock milliseconds for the Bedrock call.
    """

    image_bytes: bytes
    image_b64: str
    finish_reason: str | None
    seed: int
    model_id: str
    latency_ms: int


def _resize_image(image_bytes: bytes, image_format: str) -> tuple[bytes, str]:
    """Downscale image so neither side exceeds _MAX_IMAGE_SIDE, re-encode as JPEG."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        img.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_MAX_JPEG_QUALITY)
        return buf.getvalue(), "jpeg"


def _compress_to_fit(image_bytes: bytes, max_bytes: int) -> bytes:
    """Re-encode JPEG at decreasing quality until under max_bytes; returns empty bytes if impossible."""
    for quality in range(_MAX_JPEG_QUALITY, _MIN_JPEG_QUALITY - 1, -10):
        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            compressed = buf.getvalue()
            if len(compressed) <= max_bytes:
                return compressed
    return b""


_DEFAULT_NEGATIVE_PROMPT = (
    "ugly, deformed, blurry, low quality, artifacts, watermark, text, signature, "
    "cartoon, anime, painting, illustration, extra limbs, distorted perspective, "
    "overexposed, underexposed"
)

# These terms are always appended to the negative prompt regardless of style.
# They enforce structural immutability — SD must never render new openings or
# alter the building envelope even if the positive prompt implies it.
_STRUCTURAL_NEGATIVE_TERMS = (
    "new window, added window, extra window, new door, added door, extra door, "
    "new skylight, added skylight, new opening, new wall, removed wall, "
    "relocated window, relocated door, new archway, new columns, new balcony"
)


def _invoke_sd(
    *,
    client: object,
    model_id: str,
    prompt: str,
    control_image_b64: str,
    control_strength: float = 0.65,
    negative_prompt: str = _DEFAULT_NEGATIVE_PROMPT,
    seed: int = 0,
) -> dict:
    """Synchronous Bedrock invoke_model call to a Stability AI ControlNet model."""
    body = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "image": control_image_b64,
        "control_strength": control_strength,
        "output_format": _SD_OUTPUT_FORMAT,
        "seed": seed,
    }

    resp = client.invoke_model(  # type: ignore[attr-defined]
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(resp["body"].read())


def _build_bedrock_client(region: str) -> object:
    return boto3.client("bedrock-runtime", region_name=region)


async def generate_image(
    enriched_prompt: str,
    control_image_bytes: bytes,
    control_image_format: str,
    settings: PipelineSettings,
    seed: int = 0,
    negative_prompt: str = _DEFAULT_NEGATIVE_PROMPT,
) -> GenerationResult:
    """Invoke Stage 2: generate an image via SD ControlNet.

    The control image is resized before submission. If the generated output
    exceeds ``settings.max_output_image_bytes`` it is compressed; if it cannot
    be brought within budget it is treated as a generation failure.

    Args:
        enriched_prompt: Rewritten prompt from Stage 1.
        control_image_bytes: Raw bytes of the control (reference) image.
        control_image_format: Image format string (e.g. ``"jpeg"``).
        settings: Pipeline configuration.
        seed: Seed for deterministic generation.
        negative_prompt: Optional negative prompt.

    Returns:
        GenerationResult. ``image_bytes`` is empty on failure.

    Raises:
        Exception: Any Bedrock or network error is propagated to the caller.
    """
    client = _build_bedrock_client(settings.aws_region)

    # Resize control image to stay within Bedrock body limit
    resized_bytes, _ = _resize_image(control_image_bytes, control_image_format)
    control_b64 = base64.b64encode(resized_bytes).decode("utf-8")

    # Always append structural guard terms so SD never renders new openings
    full_negative = f"{negative_prompt}, {_STRUCTURAL_NEGATIVE_TERMS}"
    start = time.monotonic()
    raw_result: dict = await asyncio.to_thread(
        _invoke_sd,
        client=client,
        model_id=settings.sd_model_id,
        prompt=enriched_prompt,
        control_image_b64=control_b64,
        seed=seed,
        negative_prompt=full_negative,
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    seeds: list = raw_result.get("seeds", [seed])
    finish_reasons: list = raw_result.get("finish_reasons", [None])
    images: list = raw_result.get("images", [])

    used_seed = seeds[0] if seeds else seed
    finish_reason: str | None = finish_reasons[0] if finish_reasons else None

    if finish_reason is not None:
        logger.warning(
            "SD generation returned non-null finish_reason %r. model_id=%s",
            finish_reason,
            settings.sd_model_id,
        )
        return GenerationResult(
            image_bytes=b"",
            image_b64="",
            finish_reason=finish_reason,
            seed=used_seed,
            model_id=settings.sd_model_id,
            latency_ms=latency_ms,
        )

    if not images:
        logger.warning("SD response contained no images. model_id=%s", settings.sd_model_id)
        return GenerationResult(
            image_bytes=b"",
            image_b64="",
            finish_reason="no_images",
            seed=used_seed,
            model_id=settings.sd_model_id,
            latency_ms=latency_ms,
        )

    decoded = base64.b64decode(images[0])

    if len(decoded) > settings.max_output_image_bytes:
        logger.info(
            "Output image (%d bytes) exceeds limit (%d); compressing.",
            len(decoded),
            settings.max_output_image_bytes,
        )
        decoded = _compress_to_fit(decoded, settings.max_output_image_bytes)

    if not decoded:
        logger.warning(
            "Output image could not be compressed to fit %d bytes; treating as SD failure.",
            settings.max_output_image_bytes,
        )
        return GenerationResult(
            image_bytes=b"",
            image_b64="",
            finish_reason="output_too_large",
            seed=used_seed,
            model_id=settings.sd_model_id,
            latency_ms=latency_ms,
        )

    return GenerationResult(
        image_bytes=decoded,
        image_b64=base64.b64encode(decoded).decode("utf-8"),
        finish_reason=None,
        seed=used_seed,
        model_id=settings.sd_model_id,
        latency_ms=latency_ms,
    )
