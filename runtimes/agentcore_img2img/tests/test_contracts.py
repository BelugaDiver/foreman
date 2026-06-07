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
