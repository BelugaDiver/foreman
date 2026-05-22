"""Job processor for handling generation requests."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode

from foreman.db import Database
from foreman.logging_config import get_logger
from foreman.repositories import postgres_generations_repository as gen_repo
from foreman.schemas.generation import GenerationUpdate
from foreman.storage.protocol import StorageProtocol
from worker.config import WorkerConfig
from worker.consumer import GenerationJob, MalformedSQSMessageError

logger = get_logger("worker.processor")

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

    def __init__(self, db: Database, config: WorkerConfig, ai_provider, storage: StorageProtocol):
        self.db = db
        self.config = config
        self.ai_provider = ai_provider
        self._storage = storage

    async def process(self, job: GenerationJob, retry_count: int = 0) -> ProcessingResult:
        """Process a generation job."""
        logger.info(
            "Processing job", extra={"generation_id": job.generation_id, "retry": retry_count}
        )
        start_time = time.time()

        with tracer.start_as_current_span("process_generation") as span:
            span.set_attribute("generation_id", job.generation_id)
            span.set_attribute("project_id", job.project_id)
            span.set_attribute("prompt_length", len(job.prompt))
            span.set_attribute("retry_count", retry_count)

            try:
                # Validate user_id from SQS message matches generation's owner
                if not job.user_id:
                    raise MalformedSQSMessageError("No user_id in job message")

                job_user_id = UUID(job.user_id)

                # Fetch generation to verify ownership and get any additional data
                gen = await gen_repo.get_generation_by_id(
                    self.db,
                    UUID(job.generation_id),
                    job_user_id,
                )
                user_id = job_user_id

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
                span.set_status(Status(StatusCode.OK))

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
                span.set_status(Status(StatusCode.ERROR, "Job processing failed"))

                error_msg = "Internal processing error"
                if isinstance(exc, MalformedSQSMessageError):
                    error_msg = "Invalid job message format"

                user_id = None
                if job.user_id:
                    try:
                        gen = await gen_repo.get_generation_by_id(
                            self.db,
                            UUID(job.generation_id),
                            UUID(job.user_id),
                        )
                        user_id = gen.user_id
                    except Exception:
                        pass

                try:
                    await self._update_status(
                        job.generation_id,
                        user_id,
                        "failed",
                        error_message=error_msg,
                        processing_time_ms=processing_time_ms,
                    )
                except Exception:
                    logger.exception(
                        "Failed to update status to 'failed'",
                        extra={"generation_id": job.generation_id},
                    )

                raise

    async def _run_agent(self, job: GenerationJob) -> dict:
        """Run the agent graph using AI provider."""
        logger.info(
            "Running agent",
            extra={"prompt_length": len(job.prompt), "input_image": job.input_image_url},
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
        """Upload generated image via StorageProtocol and return the download URL."""
        with tracer.start_as_current_span("upload_to_storage") as span:
            storage_key = f"generations/{uuid.uuid4()}.png"
            span.set_attribute("storage_key", storage_key)
            try:
                await self._storage.upload_file(local_path, storage_key)
                url = await self._storage.get_download_url(storage_key)
                span.set_attribute("output_url", url)
                logger.info("Uploaded to storage", extra={"storage_key": storage_key})
                return url
            finally:
                try:
                    os.unlink(local_path)
                except OSError:
                    pass

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
            generation_in=update,
        )
