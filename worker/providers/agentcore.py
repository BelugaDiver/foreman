"""AWS AgentCore provider implementation."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import boto3

from foreman.logging_config import get_logger

logger = get_logger("worker.providers.agentcore")


@dataclass
class AgentCoreResult:
    """Normalized AgentCore response used by the worker processor."""

    output_image_url: str
    model_used: str
    generated_image_description: str | None = None


class AgentCoreProvider:
    """Calls AgentCore runtime and normalizes metadata-only responses."""

    def __init__(
        self,
        runtime_arn: str | None = None,
        region: str = "us-east-1",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        **_: Any,
    ):
        self.runtime_arn = runtime_arn
        self.region = region
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "bedrock-agentcore",
                region_name=self.region,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        input_image_url: str | None = None,
        style_id: str | None = None,
        runtime_session_id: str | None = None,
        generation_id: str | None = None,
        **_: Any,
    ) -> AgentCoreResult:
        """Invoke AgentCore and return normalized metadata-only response."""
        logger.info(
            "Invoking AgentCore runtime",
            extra={
                "runtime_session_id": runtime_session_id,
                "generation_id": generation_id,
                "style_id": style_id,
                "prompt": prompt,
                "input_image_url": input_image_url,
            },
        )

        payload = {
            "prompt": prompt,
            "input_image_url": input_image_url,
            "style_id": style_id,
            "generation_id": generation_id,
        }

        response = await self._invoke_runtime(payload, runtime_session_id=runtime_session_id)
        normalized = self._normalize_response(response)
        self._enforce_metadata_only(normalized)

        logger.info(
            "AgentCore runtime completed",
            extra={
                "runtime_session_id": runtime_session_id,
                "generation_id": generation_id,
                "output_image_url": normalized.get("output_image_url"),
                "generated_image_description": normalized.get("generated_image_description"),
            },
        )

        return AgentCoreResult(
            output_image_url=normalized["output_image_url"],
            model_used=normalized.get("model_used", "agentcore"),
            generated_image_description=normalized.get("generated_image_description"),
        )

    async def _invoke_runtime(
        self,
        payload: dict[str, Any],
        runtime_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Perform runtime invocation against available SDK method names."""
        if not self.runtime_arn:
            raise ValueError("AGENTCORE_RUNTIME_ARN is required for agentcore provider")

        client = self._get_client()

        def _call() -> dict[str, Any]:
            # boto3 appends /runtime-endpoint/DEFAULT automatically; strip it if
            # the caller already included it so the ARN isn't doubled.
            arn = self.runtime_arn
            if arn and arn.endswith("/runtime-endpoint/DEFAULT"):
                arn = arn[: -len("/runtime-endpoint/DEFAULT")]
            common_kwargs = {
                "agentRuntimeArn": arn,
                "payload": json.dumps(payload).encode("utf-8"),
            }
            if runtime_session_id:
                common_kwargs["runtimeSessionId"] = runtime_session_id
            for method_name in ("invoke_agent_runtime", "invoke_runtime", "invoke"):
                method = getattr(client, method_name, None)
                if callable(method):
                    return method(**common_kwargs)
            raise RuntimeError("No supported AgentCore invoke method found on boto3 client")

        return await asyncio.to_thread(_call)

    def _normalize_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Normalize possible SDK response shapes into a common dictionary."""
        if not isinstance(response, dict):
            raise ValueError("AgentCore response must be a dict")

        # The SDK returns the body as a streaming blob under the "response" key.
        # Fall back to "payload" for any future SDK shape changes.
        raw_body = response.get("response") or response.get("payload")
        if raw_body is None:
            raise ValueError("AgentCore response has no body (expected 'response' key)")

        if hasattr(raw_body, "read"):
            raw_body = raw_body.read()
        if isinstance(raw_body, (bytes, bytearray)):
            raw_body = raw_body.decode("utf-8")

        if isinstance(raw_body, str):
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                raise ValueError(f"AgentCore response body is not valid JSON: {exc}") from exc
        elif isinstance(raw_body, dict):
            payload = raw_body
        else:
            raise ValueError(f"Unexpected AgentCore response body type: {type(raw_body)}")

        artifact = payload.get("artifact", {})
        output_url = payload.get("output_image_url") or artifact.get("output_image_url")

        if not output_url:
            raise ValueError("AgentCore response missing output_image_url")

        return {
            "output_image_url": output_url,
            "generated_image_description": payload.get("generated_image_description"),
            "model_used": payload.get("model_used", "agentcore"),
            "binary_image": payload.get("binary_image"),
            "image_bytes": payload.get("image_bytes"),
            "raw_image": payload.get("raw_image"),
        }

    def _enforce_metadata_only(self, normalized: dict[str, Any]) -> None:
        """Reject responses that include raw image bytes in worker path."""
        for key in ("binary_image", "image_bytes", "raw_image"):
            if normalized.get(key) is not None:
                raise ValueError("AgentCore response must be metadata-only (no binary image data)")
