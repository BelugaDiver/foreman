"""Tests for worker/providers/agentcore.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from worker.providers.agentcore import AgentCoreProvider


@pytest.mark.asyncio
async def test_generate_normalizes_response():
    """Provider returns normalized output URL and description."""
    provider = AgentCoreProvider(
        runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test",
        region="us-east-1",
    )

    response = {
        "payload": {
            "artifact": {"output_image_url": "https://cdn.example.com/out.png"},
            "generated_image_description": "A warm interior scene",
            "model_used": "agentcore-v1",
        }
    }

    with patch.object(provider, "_invoke_runtime", return_value=response):
        result = await provider.generate(
            prompt="style this image",
            input_image_url="https://example.com/in.png",
            runtime_session_id="proj-00000000-0000-0000-0000-000000000001",
            generation_id="00000000-0000-0000-0000-000000000002",
        )

    assert result.output_image_url == "https://cdn.example.com/out.png"
    assert result.generated_image_description == "A warm interior scene"
    assert result.model_used == "agentcore-v1"


@pytest.mark.asyncio
async def test_invoke_runtime_requires_runtime_arn():
    """Provider requires runtime ARN before attempting to invoke AgentCore."""
    provider = AgentCoreProvider(runtime_arn=None)
    with pytest.raises(ValueError, match="AGENTCORE_RUNTIME_ARN"):
        await provider._invoke_runtime(payload={"prompt": "x"}, runtime_session_id="proj-1")


@pytest.mark.asyncio
async def test_invoke_runtime_uses_supported_method_name():
    """Provider should use invoke_agent_runtime when exposed by boto3 client."""
    provider = AgentCoreProvider(
        runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test",
        region="us-east-1",
    )

    client = MagicMock()
    client.invoke_agent_runtime.return_value = {"payload": {"output_image_url": "https://x"}}

    with patch("worker.providers.agentcore.boto3.client", return_value=client):
        result = await provider._invoke_runtime(
            payload={"prompt": "x"},
            runtime_session_id="proj-1",
        )

    assert result["payload"]["output_image_url"] == "https://x"
    client.invoke_agent_runtime.assert_called_once()


@pytest.mark.asyncio
async def test_invoke_runtime_omits_runtime_session_id_when_none():
    """Provider should omit runtimeSessionId when no runtime session is provided."""
    provider = AgentCoreProvider(
        runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test",
        region="us-east-1",
    )

    client = MagicMock()
    client.invoke_agent_runtime.return_value = {"payload": {"output_image_url": "https://x"}}

    with patch("worker.providers.agentcore.boto3.client", return_value=client):
        await provider._invoke_runtime(
            payload={"prompt": "x"},
            runtime_session_id=None,
        )

    client.invoke_agent_runtime.assert_called_once()
    kwargs = client.invoke_agent_runtime.call_args.kwargs
    assert "runtimeSessionId" not in kwargs


@pytest.mark.asyncio
async def test_generate_returns_output_image_bytes_when_present():
    """Provider populates output_image_bytes on AgentCoreResult when present in response."""
    import base64

    provider = AgentCoreProvider(
        runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test",
        region="us-east-1",
    )
    img_b64 = base64.b64encode(b"\xff\xd8\xff\xe0fake_jpeg").decode()

    response = {
        "payload": {
            "output_image_url": "https://cdn.example.com/out.jpg",
            "generated_image_description": "A bright room",
            "model_used": "nova-lite",
            "output_image_bytes": img_b64,
        }
    }

    with patch.object(provider, "_invoke_runtime", return_value=response):
        result = await provider.generate(
            prompt="a room",
            generation_id="gen-abc",
        )

    assert result.output_image_bytes == img_b64


@pytest.mark.asyncio
async def test_generate_output_image_bytes_absent_returns_none():
    """Provider sets output_image_bytes=None when field is absent from response."""
    provider = AgentCoreProvider(
        runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test",
        region="us-east-1",
    )

    response = {
        "payload": {
            "output_image_url": "https://cdn.example.com/out.jpg",
        }
    }

    with patch.object(provider, "_invoke_runtime", return_value=response):
        result = await provider.generate(prompt="a room", generation_id="gen-xyz")

    assert result.output_image_bytes is None
