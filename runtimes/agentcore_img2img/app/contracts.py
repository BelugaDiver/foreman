from __future__ import annotations

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator


class RuntimeInvocationRequest(BaseModel):
    """Worker-compatible invocation request accepted by the runtime host."""

    prompt: str
    generation_id: str
    input_image_url: HttpUrl | None = None
    style_id: str | None = None
    runtime_session_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("prompt", "generation_id")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("field must be a non-empty string")
        return value


class RuntimeInvocationResponse(BaseModel):
    """Runtime response returned to worker callers.

    ``output_image_bytes`` carries a base64-encoded JPEG when image generation
    succeeded. Workers decode the bytes and upload them to the storage backend.
    Extra fields are silently ignored so that adding new response fields is
    backward-compatible with older worker versions.
    """

    output_image_url: HttpUrl
    generated_image_description: str | None = None
    model_used: str | None = None
    output_image_bytes: str | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("output_image_url")
    @classmethod
    def validate_remote_url(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme not in {"http", "https"}:
            raise ValueError("output_image_url must be a remote HTTP(S) URL")
        return value
