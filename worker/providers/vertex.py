"""Google Vertex AI provider using Gemini models."""

from __future__ import annotations

import asyncio
import os
import urllib.request
from dataclasses import dataclass

from google import genai
from google.genai import types
from opentelemetry import trace

from foreman.logging_config import get_logger

logger = get_logger("worker.providers.vertex")

tracer = trace.get_tracer(__name__)


@dataclass
class ImageResult:
    output_image_url: str
    model_used: str


class GeminiProvider:
    """Google Vertex AI provider using Gemini models.

    - gemini-3.1-flash-image: Image analysis + img2img generation
    - gemini-2.0-flash: Cheaper model for prompt enhancement
    """

    def __init__(
        self,
        project_id: str | None = None,
        location: str = "us-central1",
        image_model: str = "gemini-3.1-flash-image",
        enhancement_model: str = "gemini-2.0-flash",
        allowed_image_domains: set[str] | None = None,
    ):
        self.project_id = project_id or os.getenv("GOOGLE_PROJECT_ID")
        self.location = location
        self.image_model = image_model
        self.enhancement_model = enhancement_model
        self.allowed_image_domains = allowed_image_domains or set()
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location,
            )
        return self._client

    async def enhance_prompt(self, prompt: str, input_image_url: str) -> str:
        """Enhance prompt using cheaper Gemini 2.0 Flash model."""
        with tracer.start_as_current_span("enhance_prompt") as span:
            span.set_attribute("original_prompt", prompt)
            logger.info(
                "Enhancing prompt",
                extra={"model": self.enhancement_model, "prompt_length": len(prompt)},
            )

            def _enhance():
                client = self._get_client()
                response = client.models.generate_content(
                    model=self.enhancement_model,
                    contents=[
                        f"Given this user prompt: '{prompt}'\n"
                        f"And this input image: {input_image_url}\n\n"
                        "Enhance the prompt to be more detailed for image generation. "
                        "Focus on style, composition, lighting, and colors.",
                    ],
                )
                return response.text

            enhanced = await asyncio.to_thread(_enhance)
            logger.info("Prompt enhanced", extra={"enhanced_prompt_length": len(enhanced)})
            span.set_attribute("enhanced_prompt", enhanced)
            return enhanced

    async def generate(
        self,
        prompt: str,
        input_image_url: str | None = None,
        style_id: str | None = None,
        enhance_prompt: bool = True,
    ) -> ImageResult:
        """Generate an image using Gemini 3.1 Flash Image.

        Optionally enhances prompt first using cheaper model.
        Downloads input image if it's an HTTP URL (Gemini only accepts gs:// URIs).
        """
        with tracer.start_as_current_span("generate_image") as span:
            span.set_attribute("prompt", prompt)
            span.set_attribute("has_input_image", input_image_url is not None)

            final_prompt = prompt

            if enhance_prompt and input_image_url:
                final_prompt = await self.enhance_prompt(prompt, input_image_url)

            logger.info(
                "Generating with Gemini",
                extra={
                    "prompt": final_prompt,
                    "model": self.image_model,
                    "has_input_image": input_image_url is not None,
                },
            )

            input_content = None
            if input_image_url:
                if input_image_url.startswith("http"):
                    local_path = await self._download_image(input_image_url)
                    with open(local_path, "rb") as f:
                        input_content = types.Part.from_bytes(
                            data=f.read(),
                            mime_type="image/jpeg",
                        )
                    os.unlink(local_path)
                else:
                    input_content = types.Part.from_uri(
                        file_uri=input_image_url,
                        mime_type="image/jpeg",
                    )

            def _generate():
                client = self._get_client()

                contents = []
                if input_content:
                    contents.append(input_content)
                contents.append(final_prompt)

                config = types.GenerateContentConfig(
                    response_modalities=[types.Modality.TEXT, types.Modality.IMAGE],
                    temperature=0.7,
                )

                response = client.models.generate_content(
                    model=self.image_model,
                    contents=contents,
                    config=config,
                )
                return response

            response = await asyncio.to_thread(_generate)

            if not response.candidates or not response.candidates[0].content.parts:
                raise ValueError("No candidates in model response - possible safety block or error")

            image_data = None
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_data = part.inline_data.data
                    break

            if not image_data:
                raise ValueError("No image generated in response")

            temp_path = f"/tmp/generated_{os.urandom(8).hex()}.png"
            with open(temp_path, "wb") as f:
                f.write(image_data)

            output_url = f"file://{temp_path}"

            span.set_attribute("model_used", self.image_model)
            return ImageResult(
                output_image_url=output_url,
                model_used=self.image_model,
            )

    async def _download_image(self, url: str) -> str:
        """Download image from HTTP URL to temp file."""
        # SSRF protection: validate URL domain
        if self.allowed_image_domains:
            parsed = urllib.parse.urlparse(url)
            if parsed.hostname not in self.allowed_image_domains:
                raise ValueError(f"Image URL domain not allowed: {parsed.hostname}")
            if parsed.scheme != "https":
                raise ValueError("Image URL must use HTTPS")

        temp_path = None
        try:
            with tracer.start_as_current_span("download_input_image") as span:
                span.set_attribute("url", url)
                temp_path = f"/tmp/input_{os.urandom(8).hex()}.jpg"

                def _download():
                    with urllib.request.urlopen(url, timeout=30) as response:
                        with open(temp_path, "wb") as f:
                            f.write(response.read())

                await asyncio.to_thread(_download)
                logger.info("Downloaded input image", extra={"url": url, "path": temp_path})
                return temp_path
        except Exception:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
