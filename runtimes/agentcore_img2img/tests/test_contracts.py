from __future__ import annotations

import pytest
from pydantic import ValidationError

from runtimes.agentcore_img2img.app.contracts import RuntimeInvocationRequest, RuntimeInvocationResponse


def test_request_requires_mandatory_fields() -> None:
    req = RuntimeInvocationRequest(
        prompt="test",
        generation_id="gen-1",
        input_image_url="https://cdn.example.com/input.png",
    )
    assert req.style_id is None


def test_request_rejects_empty_prompt() -> None:
    with pytest.raises(ValidationError):
        RuntimeInvocationRequest(
            prompt="   ",
            generation_id="gen-1",
            input_image_url="https://cdn.example.com/input.png",
        )


def test_response_requires_remote_output_url() -> None:
    with pytest.raises(ValidationError):
        RuntimeInvocationResponse(output_image_url="file:///tmp/out.png")


def test_request_accepts_null_input_image_url() -> None:
    req = RuntimeInvocationRequest(
        prompt="test without image",
        generation_id="gen-1",
    )
    assert req.input_image_url is None


def test_response_output_image_bytes_defaults_to_none() -> None:
    resp = RuntimeInvocationResponse(output_image_url="https://cdn.example.com/out.png")
    assert resp.output_image_bytes is None


def test_response_accepts_valid_base64_output_image_bytes() -> None:
    import base64

    payload = base64.b64encode(b"\xff\xd8\xff\xe0test").decode()
    resp = RuntimeInvocationResponse(
        output_image_url="https://cdn.example.com/out.png",
        output_image_bytes=payload,
    )
    assert resp.output_image_bytes == payload


def test_response_ignores_extra_fields() -> None:
    resp = RuntimeInvocationResponse(
        output_image_url="https://cdn.example.com/out.png",
        unknown_future_field="some_value",  # type: ignore[call-arg]
    )
    assert not hasattr(resp, "unknown_future_field")
