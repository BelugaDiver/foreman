from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from strands import Agent
except Exception:  # pragma: no cover - optional dependency in local dev
    Agent = None


@dataclass(frozen=True)
class GraphResult:
    """Result returned by runtime graph execution."""

    output_image_url: str
    generated_image_description: str | None
    model_used: str | None


class RuntimeGraphAdapter:
    """Strands-first graph adapter with safe metadata fallback behavior."""

    def __init__(self, output_base_url: str | None = None) -> None:
        self.output_base_url = output_base_url or os.getenv("RUNTIME_OUTPUT_BASE_URL", "").rstrip("/")
        self.model_used = os.getenv("RUNTIME_MODEL_USED", "strands-runtime")
        self._agent = None
        if Agent is not None:
            try:
                self._agent = Agent()
            except Exception:
                self._agent = None

    def _build_description(self, prompt: str, style_id: str | None) -> str:
        if self._agent is not None:
            try:
                response = self._agent(
                    f"Summarize this image generation intent in one sentence: {prompt}"
                )
                summary = str(response).strip()
                if summary:
                    return summary
            except Exception:
                pass

        description = f"Generated from prompt: {prompt[:120]}"
        if style_id:
            description = f"{description} (style: {style_id})"
        return description

    def run(
        self,
        *,
        generation_id: str,
        prompt: str,
        input_image_url: str,
        style_id: str | None,
    ) -> GraphResult:
        if not self.output_base_url:
            raise ValueError("RUNTIME_OUTPUT_BASE_URL must be configured")

        output_image_url = f"{self.output_base_url}/{generation_id}.png"
        description = self._build_description(prompt, style_id)

        _ = input_image_url
        return GraphResult(
            output_image_url=output_image_url,
            generated_image_description=description,
            model_used=self.model_used,
        )
