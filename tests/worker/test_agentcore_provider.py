"""Tests for worker/providers/agentcore.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from worker.providers.agentcore import AgentCoreProvider


@pytest.mark.asyncio
async def test_generate_normalizes_response_and_enforces_metadata_only():
    """Provider returns normalized output URL and description for metadata-only payloads."""
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
async def test_generate_rejects_binary_payload_fields():
    """Provider rejects responses that include raw image bytes in worker path."""
    provider = AgentCoreProvider(
        runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test",
        region="us-east-1",
    )

    response = {
        "payload": {
            "output_image_url": "https://cdn.example.com/out.png",
            "binary_image": "AAECAw==",
        }
    }

    with patch.object(provider, "_invoke_runtime", return_value=response):
        with pytest.raises(ValueError, match="metadata-only"):
            await provider.generate(prompt="x")


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
