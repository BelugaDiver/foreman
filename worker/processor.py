"""Job processor for handling generation requests."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from uuid import UUID

from opentelemetry import trace

from foreman.db import Database
from foreman.repositories import postgres_generations_repository as gen_repo
from foreman.schemas.generation import GenerationUpdate
from worker.config import WorkerConfig
from worker.consumer import GenerationJob

logger = logging.getLogger("worker.processor")

tracer = trace.get_tracer(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a generation job."""

    success: bool
    output_image_url: str | None = None
    error_message: str | None = None
    processing_time_ms: int | None = None
    retry_count: int = 0


class JobProcessor:
    """Processes generation jobs.

    Reuses foreman's Database and repositories directly.
    Includes OTEL tracing for observability.
    """

    def __init__(self, db: Database, config: WorkerConfig, ai_provider):
        self.db = db
        self.config = config
        self.ai_provider = ai_provider

    async def process(self, job: GenerationJob, retry_count: int = 0) -> ProcessingResult:
        """Process a generation job."""
        logger.info(
            "Processing job", extra={"generation_id": job.generation_id, "retry": retry_count}
        )
        start_time = time.time()

        with tracer.start_as_current_span("process_generation") as span:
            span.set_attribute("generation_id", job.generation_id)
            span.set_attribute("project_id", job.project_id)
            span.set_attribute("prompt", job.prompt)
            span.set_attribute("retry_count", retry_count)

            try:
                gen = await gen_repo.get_generation(
                    self.db,
                    UUID(job.generation_id),
                )
                if not gen:
                    raise ValueError(f"Generation {job.generation_id} not found")
                user_id = gen.user_id

                await self._update_status(job.generation_id, user_id, "processing")
                span.add_event("status_updated_to_processing")

                result = await self._run_agent(job)
                span.add_event("agent_completed")

                output_url = await self._upload_to_storage(result["output_image_path"])
                span.add_event("uploaded_to_storage")

                processing_time_ms = int((time.time() - start_time) * 1000)

                await self._update_status(
                    job.generation_id,
                    user_id,
                    "completed",
                    output_image_url=output_url,
                    processing_time_ms=processing_time_ms,
                )

                span.set_attribute("output_image_url", output_url)
                span.set_attribute("processing_time_ms", processing_time_ms)
                span.set_status(trace.StatusCode.OK)

                return ProcessingResult(
                    success=True,
                    output_image_url=output_url,
                    processing_time_ms=processing_time_ms,
                    retry_count=retry_count,
                )

            except Exception as exc:
                processing_time_ms = int((time.time() - start_time) * 1000)
                logger.exception("Job failed", extra={"generation_id": job.generation_id})

                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))

                try:
                    gen = await gen_repo.get_generation(self.db, UUID(job.generation_id))
                    user_id = gen.user_id if gen else None
                except Exception:
                    user_id = None

                await self._update_status(
                    job.generation_id,
                    user_id,
                    "failed",
                    error_message=str(exc),
                    processing_time_ms=processing_time_ms,
                )

                return ProcessingResult(
                    success=False,
                    error_message=str(exc),
                    processing_time_ms=processing_time_ms,
                    retry_count=retry_count,
                )

    async def _run_agent(self, job: GenerationJob) -> dict:
        """Run the agent graph using AI provider."""
        logger.info(
            "Running agent", extra={"prompt": job.prompt, "input_image": job.input_image_url}
        )

        result = await self.ai_provider.generate(
            prompt=job.prompt,
            input_image_url=job.input_image_url if job.input_image_url else None,
            style_id=job.style_id,
            enhance_prompt=True,
        )

        return {
            "output_image_path": result.output_image_url.replace("file://", ""),
            "model_used": result.model_used,
        }

    async def _upload_to_storage(self, local_path: str) -> str:
        """Upload generated image to R2 storage and return public URL."""
        import boto3
        from botocore.config import Config as BotoConfig

        filename = f"generations/{uuid.uuid4()}.png"

        client = boto3.client(
            "s3",
            endpoint_url=self.config.r2_endpoint or None,
            aws_access_key_id=self.config.r2_access_key_id,
            aws_secret_access_key=self.config.r2_secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )

        with open(local_path, "rb") as f:
            client.upload_fileobj(
                f,
                self.config.r2_bucket,
                filename,
                ExtraArgs={"ContentType": "image/png"},
            )

        if self.config.r2_endpoint:
            public_url = f"{self.config.r2_endpoint}/{filename}"
        else:
            public_url = f"https://{self.config.r2_bucket}.r2.cloudflarestorage.com/{filename}"

        logger.info("Uploaded to R2", extra={"url": public_url})

        import os

        os.unlink(local_path)

        return public_url

    async def _update_status(
        self,
        generation_id: str,
        user_id: UUID | None,
        status: str,
        output_image_url: str | None = None,
        error_message: str | None = None,
        processing_time_ms: int | None = None,
    ):
        """Update generation status in database."""
        if user_id is None:
            logger.warning(
                "Cannot update generation without user_id", extra={"generation_id": generation_id}
            )
            return

        gen_id = UUID(generation_id)

        update = GenerationUpdate(
            status=status,
            output_image_url=output_image_url,
            error_message=error_message,
            processing_time_ms=processing_time_ms,
        )

        await gen_repo.update_generation(
            self.db,
            generation_id=gen_id,
            user_id=user_id,
            gen_in=update,
        )
