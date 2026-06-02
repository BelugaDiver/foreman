from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx

try:
    from strands import Agent
except Exception:  # pragma: no cover - optional dependency in local dev
    Agent = None

try:
    from strands.models import BedrockModel
except Exception:  # pragma: no cover - optional dependency in local dev
    BedrockModel = None


_STRANDS_MODEL_ID = os.getenv("RUNTIME_STRANDS_MODEL_ID", "").strip()

if Agent is not None:
    try:
        if BedrockModel is not None and _STRANDS_MODEL_ID:
            _AGENT = Agent(model=BedrockModel(model_id=_STRANDS_MODEL_ID))
        else:
            _AGENT = Agent()
    except Exception:
        _AGENT = None
else:
    _AGENT = None

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


def _invoke_agent(
    prompt: str,
    style_id: str | None,
    image_bytes: bytes | None,
    image_format: str | None,
) -> str:
    """Invoke Strands agent with text + optional image. Returns generated description."""
    if _AGENT is not None:
        try:
            if image_bytes and image_format:
                message = [
                    {
                        "text": (
                            f"Describe the transformation of this image based on "
                            f"the following instruction: {prompt}"
                        )
                    },
                    {"image": {"format": image_format, "source": {"bytes": image_bytes}}},
                ]
            else:
                message = f"Summarize this image generation intent in one sentence: {prompt}"
            response = _AGENT(message)
            summary = str(response).strip()
            if summary:
                return summary
        except Exception:
            pass

    description = f"Generated from prompt: {prompt[:120]}"
    if style_id:
        description = f"{description} (style: {style_id})"
    return description


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
