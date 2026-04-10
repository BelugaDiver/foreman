"""Job processor for handling generation requests."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from uuid import UUID

import boto3
from botocore.config import Config as BotoConfig
from opentelemetry import trace

from foreman.db import Database
from foreman.logging_config import get_logger
from foreman.repositories import postgres_generations_repository as gen_repo
from foreman.schemas.generation import GenerationUpdate
from worker.config import WorkerConfig
from worker.consumer import GenerationJob

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
                # Validate user_id from SQS message matches generation's owner
                if not job.user_id:
                    raise ValueError("No user_id in job message")

                job_user_id = UUID(job.user_id)

                # Fetch generation to verify ownership and get any additional data
                gen = await gen_repo.get_generation_by_id(
                    self.db,
                    UUID(job.generation_id),
                    job_user_id,
                )
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
        filename = f"generations/{uuid.uuid4()}.png"

        # Robust endpoint handling
        endpoint_url = self.config.r2_endpoint
        if not endpoint_url:
            if not self.config.r2_account_id:
                raise ValueError("Neither R2_ENDPOINT nor R2_ACCOUNT_ID is configured")
            endpoint_url = f"https://{self.config.r2_account_id}.r2.cloudflarestorage.com"

        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
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
            # If we have an endpoint (possibly a custom domain), use it
            public_url = f"{self.config.r2_endpoint.rstrip('/')}/{filename}"
        else:
            # Fallback to default R2 public URL format (bucket.account_id.r2.dev or similar)
            # Cloudflare suggests using the custom domain if available,
            # otherwise bucket.account.r2.cloudflarestorage.com is the S3 API endpoint.
            # Usually users have a public bucket URL configured.
            public_url = (
                f"https://{self.config.r2_bucket}.{self.config.r2_account_id}.r2.dev/{filename}"
            )

        logger.info("Uploaded to R2", extra={"url": public_url})

        if os.path.exists(local_path):
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
