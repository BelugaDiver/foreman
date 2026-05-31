from __future__ import annotations

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator


class RuntimeInvocationRequest(BaseModel):
    """Worker-compatible invocation request accepted by the runtime host."""

    prompt: str
    generation_id: str
    input_image_url: HttpUrl
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
    """Metadata-only runtime response returned to existing worker callers."""

    output_image_url: HttpUrl
    generated_image_description: str | None = None
    model_used: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("output_image_url")
    @classmethod
    def validate_remote_url(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme not in {"http", "https"}:
            raise ValueError("output_image_url must be a remote HTTP(S) URL")
        return value
