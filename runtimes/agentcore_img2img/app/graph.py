from __future__ import annotations

import base64
import io
import json
import os
from urllib.parse import urlparse

import boto3
import httpx
from PIL import Image

_STRANDS_MODEL_ID = os.getenv("RUNTIME_STRANDS_MODEL_ID", "").strip()
_BEDROCK_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-2")

try:
    _BEDROCK = boto3.client("bedrock-runtime", region_name=_BEDROCK_REGION)
except Exception:  # pragma: no cover
    _BEDROCK = None

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


def _fetch_image(url: str) -> tuple[bytes, str] | None:
    """Fetch image bytes and format from URL. Returns (bytes, format) or None on failure."""
    try:
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
    except Exception:
        return None


_MAX_IMAGE_SIDE = 512  # px — keeps base64 payload well under body size limit


def _resize_image(image_bytes: bytes, image_format: str) -> tuple[bytes, str]:
    """Downscale image so neither side exceeds _MAX_IMAGE_SIDE, re-encode as JPEG."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        img.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "jpeg"


def _invoke_agent(
    prompt: str,
    style_id: str | None,
    image_bytes: bytes | None,
    image_format: str | None,
) -> str:
    """Call Bedrock invoke_model (Chat Completions format) to get a design response."""
    if not _BEDROCK or not _STRANDS_MODEL_ID:
        description = f"Design brief: {prompt[:120]}"
        return f"{description} (style: {style_id})" if style_id else description

    style_clause = f" Apply the following design style: {style_id}." if style_id else ""
    system_text = (
        "You are an expert interior and exterior design consultant and architect. "
        "You provide detailed, professional design recommendations in response to client briefs. "
        "Always respond with at least 3 sentences. "
        "Use Markdown formatting: **bold** key design decisions and material choices, "
        "use bullet points to list specific elements such as lighting, materials, "
        "colour palette, furniture, and spatial layout, "
        "and end with a sentence capturing the overall atmosphere or design intent."
    )

    if image_bytes and image_format:
        image_bytes, image_format = _resize_image(image_bytes, image_format)
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        user_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{image_format};base64,{b64}"},
            },
            {
                "type": "text",
                "text": (
                    f"A client has submitted this image along with the following design request: "
                    f"**{prompt}**{style_clause} "
                    f"Describe the transformation you would apply to this space."
                ),
            },
        ]
    else:
        user_content = (
            f"A client has submitted the following design brief: "
            f"**{prompt}**{style_clause} "
            f"Provide your professional design recommendations."
        )

    try:
        body = {
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 1024,
            "temperature": 0.7,
        }
        resp = _BEDROCK.invoke_model(
            modelId=_STRANDS_MODEL_ID,
            body=json.dumps(body),
        )
        result = json.loads(resp["body"].read())
        output = result["choices"][0]["message"]["content"].strip()
        if output:
            return output
    except Exception as exc:
        return f"[invoke error: {type(exc).__name__}: {exc}]"

    description = f"Design brief: {prompt[:120]}"
    return f"{description} (style: {style_id})" if style_id else description


def run_graph(
    *,
    generation_id: str,
    prompt: str,
    input_image_url: str | None,
    style_id: str | None,
) -> dict[str, str | None]:
    """Run one runtime graph invocation and return metadata-only response fields."""

    output_base_url = os.getenv("RUNTIME_OUTPUT_BASE_URL", "").rstrip("/")
    model_used = (
        os.getenv("RUNTIME_MODEL_USED", "").strip()
        or _STRANDS_MODEL_ID
        or "strands-runtime"
    )

    if not output_base_url:
        raise ValueError("RUNTIME_OUTPUT_BASE_URL must be configured")

    image_bytes: bytes | None = None
    image_format: str | None = None
    if input_image_url:
        fetched = _fetch_image(input_image_url)
        if fetched:
            image_bytes, image_format = fetched

    return {
        "output_image_url": f"{output_base_url}/{generation_id}.png",
        "generated_image_description": _invoke_agent(prompt, style_id, image_bytes, image_format),
        "model_used": model_used,
    }
