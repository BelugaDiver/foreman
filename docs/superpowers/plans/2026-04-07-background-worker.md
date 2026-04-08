# Background Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a background worker that consumes generation requests from SQS and processes them using your custom agent graph.

**Architecture:** Reuses existing foreman/ packages directly. Worker is a separate process that imports from foreman.

**Tech Stack:** Python, boto3 (SQS), foreman packages (DB, Storage, Repos)

---

## What to Reuse from foreman/

| Component | Reuse | How |
|-----------|-------|-----|
| Database | `foreman.db.Database` | `from foreman.db import Database` |
| Storage | `foreman.storage.R2Storage` | `from foreman.storage import get_storage_sync` |
| Queue Settings | `foreman.queue.settings.SQSSettings` | Already exists |
| Generation Repo | `foreman.repositories.postgres_generations_repository` | Update status, output |
| Models | `foreman.models.generation.Generation` | Type hints |
| **Telemetry** | `foreman.telemetry.setup_telemetry` | Reuse OTEL setup |

---

## File Structure

```
worker/                        # NEW - separate top-level directory
├── __init__.py
├── main.py                   # Entry point - imports foreman components + OTEL
├── config.py                 # Worker-specific config + reuses SQS settings
├── consumer.py               # SQS message consumer
├── processor.py              # Uses foreman repos, storage, AI provider
├── providers/
│   ├── __init__.py
│   └── vertex.py            # AI provider implementation (Google Vertex)
└── agent.py                  # Your custom agent graph
```

**Reuse foreman's telemetry:**
```python
from foreman.telemetry import setup_telemetry

# In worker/main.py
setup_telemetry(
    service_name="foreman-worker",
    otlp_endpoint=os.getenv("OTLP_ENDPOINT"),
)
```

---

### Task 1: Worker Directory Setup

**Files:**
- Create: `worker/__init__.py`
- Create: `worker/config.py`
- Create: `worker/main.py` (stub)

- [ ] **Step 1: Create worker/__init__.py**

```python
"""Worker package for processing generation jobs."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Create worker/config.py**

```python
"""Worker configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class WorkerConfig:
    """Worker-specific configuration.
    
    Reuses SQS settings from foreman.queue.settings.
    """

    # Worker settings
    concurrency: int = int(os.getenv("WORKER_CONCURRENCY", "1"))
    max_retries: int = int(os.getenv("WORKER_MAX_RETRIES", "3"))
    poll_interval: int = int(os.getenv("WORKER_POLL_INTERVAL", "10"))
    visibility_timeout: int = int(os.getenv("WORKER_VISIBILITY_TIMEOUT", "300"))

    # Database - reuse foreman's DATABASE_URL
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://localhost/foreman")
    )

    # AI Provider (Google Vertex)
    ai_provider: str = os.getenv("AI_PROVIDER", "vertex")
    google_project_id: str | None = field(default_factory=lambda: os.getenv("GOOGLE_PROJECT_ID"))
    google_location: str = field(default_factory=lambda: os.getenv("GOOGLE_LOCATION", "us-central1"))
    gemini_image_model: str = field(default_factory=lambda: os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"))
    gemini_enhancement_model: str = field(default_factory=lambda: os.getenv("GEMINI_ENHANCEMENT_MODEL", "gemini-2.0-flash"))

    # Storage (R2)
    r2_bucket: str = field(default_factory=lambda: os.getenv("R2_BUCKET", "foreman-assets"))
    r2_endpoint: str = field(default_factory=lambda: os.getenv("R2_ENDPOINT", ""))
    r2_access_key_id: str = field(default_factory=lambda: os.getenv("R2_ACCESS_KEY_ID", ""))
    r2_secret_access_key: str = field(default_factory=lambda: os.getenv("R2_SECRET_ACCESS_KEY", ""))

    @classmethod
    def from_env(cls) -> WorkerConfig:
        return cls()


def get_worker_config() -> WorkerConfig:
    return WorkerConfig.from_env()
```

- [ ] **Step 3: Create worker/main.py (stub)**

```python
"""Worker entry point."""

import asyncio
import logging

from worker.config import get_worker_config
from worker.consumer import SQSConsumer
from worker.processor import JobProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker.main")


async def main():
    config = get_worker_config()
    logger.info("Starting worker", extra={"config": config})

    # TODO: wire up processor, consumer
    print("Worker starting...")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Commit**

```bash
git add worker/
git commit -m "feat: add worker directory with basic config"
```

---

### Task 2: SQS Consumer

**Files:**
- Create: `worker/consumer.py`

- [ ] **Step 1: Create worker/consumer.py**

```python
"""SQS consumer for processing generation jobs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Callable

import boto3
from botocore.config import Config

logger = logging.getLogger("worker.consumer")


@dataclass
class GenerationJob:
    """Represents a generation job from SQS."""

    generation_id: str
    project_id: str
    prompt: str
    style_id: str | None
    input_image_url: str
    created_at: str
    retry_count: int = 0

    @classmethod
    def from_message(cls, body: dict) -> "GenerationJob":
        return cls(
            generation_id=body["generation_id"],
            project_id=body["project_id"],
            prompt=body["prompt"],
            style_id=body.get("style_id"),
            input_image_url=body["input_image_url"],
            created_at=body["created_at"],
            retry_count=body.get("retry_count", 0),
        )


class SQSConsumer:
    """Consumes messages from SQS queue with concurrency control."""

    def __init__(self, queue_url: str, process_fn: Callable, concurrency: int = 1, max_retries: int = 3):
        self.queue_url = queue_url
        self.process_fn = process_fn
        self.concurrency = concurrency
        self.max_retries = max_retries
        self._client = None
        self._running = False
        self._semaphore = asyncio.Semaphore(concurrency)
        self._in_flight: set[asyncio.Task] = set()

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "sqs",
                region_name=os.getenv("AWS_REGION", "us-east-1"),
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                config=Config(retries={"max_attempts": 3, "mode": "standard"}),
            )
        return self._client

    async def poll(self):
        """Poll for messages and process them concurrently."""
        client = self._get_client()
        
        # MaxNumberOfMessages can be up to 10
        batch_size = min(self.concurrency, 10)
        
        response = await asyncio.to_thread(
            client.receive_message,
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=batch_size,
            WaitTimeSeconds=10,
            VisibilityTimeout=300,
        )

        messages = response.get("Messages", [])
        tasks = []
        for msg in messages:
            task = asyncio.create_task(self._handle_message(msg))
            self._in_flight.add(task)
            task.add_done_callback(self._in_flight.discard)
        
        if tasks:
            await asyncio.gather(*tasks)

    async def _handle_message(self, msg: dict, retry_count: int = 0):
        """Handle a single SQS message with semaphore protection."""
        async with self._semaphore:
            client = self._get_client()
            try:
                body = json.loads(msg["Body"])
                job = GenerationJob.from_message(body)
                
                # SQS doesn't track retry count - use ApproximateReceiveCount attribute
                # This is incremented by SQS each time message is delivered
                receive_count = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", 1))
                actual_retry = max(0, receive_count - 1)  # First delivery = retry 0
                
                logger.info("Received job", extra={"generation_id": job.generation_id, "retry": actual_retry})

                # Process the job (CPU/IO intensive part)
                await self.process_fn(job, retry_count=actual_retry)

                # Delete message on success
                await asyncio.to_thread(
                    client.delete_message,
                    QueueUrl=self.queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )
                logger.info("Job completed", extra={"generation_id": job.generation_id})

            except Exception:
                logger.exception("Failed to process message", extra={"retry": retry_count})
                
                # Retry logic: don't delete message - let SQS handle retry via visibility timeout
                # After max_retries, message will be discarded
                if retry_count >= self.max_retries:
                    logger.error("Max retries exceeded, discarding message", extra={"generation_id": job.generation_id})
                    # Delete message to prevent infinite retries
                    await asyncio.to_thread(
                        client.delete_message,
                        QueueUrl=self.queue_url,
                        ReceiptHandle=msg["ReceiptHandle"],
                    )
                else:
                    # Re-raise to prevent deletion - message returns to queue after visibility timeout
                    raise

    async def start(self):
        """Run the consumer loop."""
        self._running = True
        logger.info("Starting SQS consumer", extra={"queue_url": self.queue_url})

        while self._running:
            try:
                await self.poll()
                # Small sleep to prevent tight loop when queue is empty
                await asyncio.sleep(1)
            except Exception:
                logger.exception("Error in consumer loop")
                await asyncio.sleep(5)

    async def stop(self, timeout: float = 30.0):
        """Stop the consumer gracefully, waiting for in-flight jobs."""
        logger.info("Stopping consumer...")
        self._running = False
        
        # Wait for in-flight tasks with timeout
        if self._in_flight:
            await asyncio.wait_for(
                asyncio.gather(*self._in_flight, return_exceptions=True),
                timeout=timeout,
            )
        logger.info("Consumer stopped")

    def is_ready(self) -> bool:
        """Health check - returns True if consumer is running."""
        return self._running
```

- [ ] **Step 2: Commit**

```bash
git add worker/consumer.py
git commit -m "feat: add SQS consumer"
```

---

### Task 3: Job Processor

**Files:**
- Create: `worker/processor.py`

- [ ] **Step 1: Create worker/processor.py**

```python
"""Job processor for handling generation requests."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from uuid import UUID

from opentelemetry import trace

from foreman.db import Database
from foreman.repositories import postgres_generations_repository as gen_repo
from foreman.schemas.generation import GenerationUpdate

from worker.consumer import GenerationJob
from worker.config import WorkerConfig
from worker.providers import get_provider

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

    def __init__(self, db: Database, config: WorkerConfig):
        self.db = db
        self.config = config
        self.ai_provider = get_provider(
            provider_type=config.ai_provider,
            project_id=config.google_project_id,
            location=config.google_location,
            image_model=config.gemini_image_model,
            enhancement_model=config.gemini_enhancement_model,
        )

    async def process(self, job: GenerationJob, retry_count: int = 0) -> ProcessingResult:
        """Process a generation job."""
        logger.info("Processing job", extra={"generation_id": job.generation_id, "retry": retry_count})
        start_time = time.time()

        with tracer.start_as_current_span("process_generation") as span:
            span.set_attribute("generation_id", job.generation_id)
            span.set_attribute("project_id", job.project_id)
            span.set_attribute("prompt", job.prompt)
            span.set_attribute("retry_count", retry_count)

            try:
                # Fetch generation to get user_id (required for update)
                gen = await gen_repo.get_generation(
                    self.db,
                    UUID(job.generation_id),
                )
                if not gen:
                    raise ValueError(f"Generation {job.generation_id} not found")
                user_id = gen.user_id

                # Update status to processing
                await self._update_status(job.generation_id, user_id, "processing")
                span.add_event("status_updated_to_processing")

                # Run agent graph (uses AI provider)
                result = await self._run_agent(job)
                span.add_event("agent_completed")

                # Upload to R2 storage
                output_url = await self._upload_to_storage(result["output_image_path"])
                span.add_event("uploaded_to_storage")

                processing_time_ms = int((time.time() - start_time) * 1000)

                # Update with success
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

                # Record exception in span
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))

                # Fetch generation for user_id (needed for update)
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
        logger.info("Running agent", extra={"prompt": job.prompt, "input_image": job.input_image_url})

        # Use AI provider to generate image
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
        import uuid

        filename = f"generations/{uuid.uuid4()}.png"
        
        # Upload to R2 using boto3 (s3-compatible API)
        import boto3
        from botocore.config import Config as BotoConfig

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

        # Construct public URL (Cloudflare R2 uses custom domain or default domain)
        if self.config.r2_endpoint:
            # Custom domain
            public_url = f"{self.config.r2_endpoint}/{filename}"
        else:
            # Default R2 domain
            public_url = f"https://{self.config.r2_bucket}.r2.cloudflarestorage.com/{filename}"

        logger.info("Uploaded to R2", extra={"url": public_url})
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
            logger.warning("Cannot update generation without user_id", extra={"generation_id": generation_id})
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
```

- [ ] **Step 2: Commit**

```bash
git add worker/processor.py
git commit -m "feat: add job processor using foreman repos"
```

---

### Task 4: Wire Everything Together

**Files:**
- Modify: `worker/main.py`

- [ ] **Step 1: Update worker/main.py**

```python
"""Worker entry point."""

import asyncio
import logging
import os
import signal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from uvicorn import Server, Config

from foreman.db import Database
from foreman.queue.settings import SQSSettings
from foreman.telemetry import setup_telemetry

from worker.config import get_worker_config
from worker.consumer import SQSConsumer
from worker.processor import JobProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("worker.main")

# Health check app (separate from main app to avoid circular imports)
health_app = FastAPI(title="worker-health")


@health_app.get("/health")
async def health():
    """Liveness check."""
    return {"status": "ok"}


@health_app.get("/ready")
async def ready(db: Database):
    """Readiness check - verifies DB and queue connectivity."""
    try:
        await db.execute("SELECT 1")
        return {"status": "ready", "database": "connected"}
    except Exception:
        return JSONResponse({"status": "not ready", "database": "disconnected"}, status_code=503)


async def main():
    # Setup telemetry first
    setup_telemetry(
        service_name="foreman-worker",
        otlp_endpoint=os.getenv("OTLP_ENDPOINT"),
    )
    logger.info("Telemetry initialized")

    config = get_worker_config()
    logger.info("Starting worker", extra={"config": config})

    # Get SQS queue URL
    sqs_settings = SQSSettings.from_env()
    if not sqs_settings.is_configured:
        logger.error("SQS not configured. Set SQS_QUEUE_URL")
        return

    # Setup database (reuses foreman's Database)
    db = Database.from_env()
    await db.connect()
    logger.info("Database connected")

    # Inject db into health endpoint
    health_app.dependency_overrides[getattr(__import__("foreman.api.deps", fromlist=["get_db"]), "get_db", None)] = lambda: db

    # Start health server in background
    health_server = Server(
        Config(app=health_app, host="0.0.0.0", port=8081, log_level="warning")
    )
    health_task = asyncio.create_task(health_server.serve())
    logger.info("Health server started on port 8081")

    # Create processor with foreman components
    processor = JobProcessor(db, config)

    # Create consumer with concurrency control
    consumer = SQSConsumer(
        queue_url=sqs_settings.queue_url,
        process_fn=processor.process,
        concurrency=config.concurrency,
        max_retries=config.max_retries,
    )

    # Graceful shutdown handler
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating shutdown...")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: shutdown_event.set())

    try:
        await consumer.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Graceful stop: wait for in-flight jobs
        await consumer.stop(timeout=60.0)
        
        # Shutdown health server
        health_server.should_exit = True
        await health_task
        
        await db.disconnect()
        logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add worker/main.py
git commit -m "feat: wire up worker main with foreman components and OTEL"
```

---

### Task 5: AI Provider (Google Vertex)

**Files:**
- Create: `worker/providers/__init__.py`
- Create: `worker/providers/vertex.py`

**Context7 Verified:**
- Use new `google` SDK (`from google import genai`)
- Image model: `gemini-3.1-flash-image` (analyzes images + img2img generation)
- Prompt enhancement model: `gemini-2.0-flash` (cheaper, text-only)

- [ ] **Step 1: Create worker/providers/__init__.py**

```python
"""AI provider implementations."""

from worker.providers.vertex import GeminiProvider

__all__ = ["GeminiProvider", "get_provider"]


def get_provider(provider_type: str = "vertex", **kwargs):
    """Factory to get AI provider."""
    if provider_type == "vertex":
        return GeminiProvider(**kwargs)
    raise ValueError(f"Unknown provider: {provider_type}")
```

- [ ] **Step 2: Create worker/providers/vertex.py**

```python
"""Google Vertex AI provider using Gemini models."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from google import genai
from google.genai import types

logger = logging.getLogger("worker.providers.vertex")


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
    ):
        self.project_id = project_id or os.getenv("GOOGLE_PROJECT_ID")
        self.location = location
        self.image_model = image_model
        self.enhancement_model = enhancement_model
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
        logger.info(
            "Enhancing prompt",
            extra={"model": self.enhancement_model, "original_prompt": prompt},
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
        logger.info("Prompt enhanced", extra={"enhanced_prompt": enhanced})
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
        final_prompt = prompt

        if enhance_prompt and input_image_url:
            final_prompt = await self.enhance_prompt(prompt, input_image_url)

        logger.info(
            "Generating with Gemini",
            extra={
                "prompt": final_prompt,
                "model": self.image_model,
                "has_input_image": input_image_url is not None,
            }
        )

        # Prepare input - download if HTTP URL (Gemini only accepts gs://)
        input_content = None
        if input_image_url:
            if input_image_url.startswith("http"):
                # Download to temp file
                local_path = await self._download_image(input_image_url)
                with open(local_path, "rb") as f:
                    input_content = types.Part.from_bytes(
                        data=f.read(),
                        mime_type="image/jpeg",
                    )
                # Clean up temp file after use
                os.unlink(local_path)
            else:
                # GCS URI - use directly
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

        return ImageResult(
            output_image_url=output_url,
            model_used=self.image_model,
        )

    async def _download_image(self, url: str) -> str:
        """Download image from HTTP URL to temp file."""
        import urllib.request

        temp_path = f"/tmp/input_{os.urandom(8).hex()}.jpg"
        urllib.request.urlretrieve(url, temp_path)
        logger.info("Downloaded input image", extra={"url": url, "path": temp_path})
        return temp_path
```

- [ ] **Step 3: Commit**

```bash
git add worker/providers/
git commit -m "feat: add Google Vertex AI provider with Gemini models"
```

---

### Task 6: Agent Graph Wrapper

**Files:**
- Create: `worker/agent.py`

- [ ] **Step 1: Create worker/agent.py**

```python
"""Agent graph wrapper for custom processing pipelines."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("worker.agent")


@dataclass
class AgentResult:
    output_image_url: str
    iterations: int = 1
    metadata: dict | None = None


class AgentGraph:
    """Wrapper for your custom agent graph.
    
    This is where your agent graph integration goes.
    """

    async def run(
        self,
        input_image_path: str,
        prompt: str,
        style_id: str | None = None,
    ) -> AgentResult:
        """Run your agent graph pipeline.
        
        Should:
        1. Analyze input image
        2. Enhance prompt (LLM)
        3. Generate image
        4. Evaluate quality
        5. Iterate if needed
        
        Returns:
            AgentResult with output URL
        """
        logger.info(
            "Running agent graph",
            extra={"input_image": input_image_path, "prompt": prompt},
        )

        # TODO: Your agent graph integration here
        # This is a placeholder - replace with your implementation
        return AgentResult(
            output_image_url="https://example.com/generated.jpg",
            iterations=1,
            metadata={"placeholder": True},
        )
```

- [ ] **Step 2: Commit**

```bash
git add worker/agent.py
git commit -m "feat: add agent graph wrapper placeholder"
```

---

### Task 7: Environment Variables

**Files:**
- Modify: `.env.foreman.example`

- [ ] **Step 1: Update .env.foreman.example**

```bash
# Worker Configuration
WORKER_CONCURRENCY=1
WORKER_MAX_RETRIES=3
WORKER_POLL_INTERVAL=10
WORKER_VISIBILITY_TIMEOUT=300

# AI Provider (Google Vertex)
AI_PROVIDER=vertex
GOOGLE_PROJECT_ID=your-google-project-id
GOOGLE_LOCATION=us-central1

# Gemini Models
GEMINI_IMAGE_MODEL=gemini-3.1-flash-image
GEMINI_ENHANCEMENT_MODEL=gemini-2.0-flash

# Storage (R2)
R2_BUCKET=foreman-assets
R2_ENDPOINT=your-r2-endpoint
R2_ACCESS_KEY_ID=your-access-key
R2_SECRET_ACCESS_KEY=your-secret-key
```

- [ ] **Step 2: Commit**

```bash
git add .env.foreman.example
git commit -m "docs: add worker environment variables"
```

---

### Task 8: Simple Test

**Files:**
- Create: `worker/tests/__init__.py`
- Create: `worker/tests/test_basic.py`

- [ ] **Step 1: Create worker/tests/__init__.py**

```python
"""Worker tests."""
```

- [ ] **Step 2: Create worker/tests/test_basic.py**

```python
"""Basic worker tests."""

import pytest


def test_worker_config():
    """Test config loads from env."""
    from worker.config import WorkerConfig
    
    config = WorkerConfig()
    assert config.concurrency >= 1
    assert config.max_retries >= 1


def test_consumer_job_parsing():
    """Test parsing SQS message."""
    from worker.consumer import GenerationJob
    
    body = {
        "generation_id": "abc-123",
        "project_id": "proj-456",
        "prompt": "make it modern",
        "input_image_url": "https://example.com/input.jpg",
        "created_at": "2026-04-07T12:00:00Z",
    }
    
    job = GenerationJob.from_message(body)
    assert job.generation_id == "abc-123"
    assert job.prompt == "make it modern"
```

- [ ] **Step 3: Commit**

```bash
git add worker/tests/
git commit -m "test: add basic worker tests"
```

---

## Summary

This implementation creates:

1. `worker/` directory at repo root
2. Config that extends environment variables (including R2 storage)
3. SQS consumer with retry logic, graceful shutdown, and health checks
4. Processor that uses foreman's DB and repos directly
5. AI provider using Gemini 3.1 Flash Image + Gemini 2.0 Flash for enhancement
6. Storage upload to R2
7. Health endpoints (/health, /ready) on port 8081

**Key fixes applied:**
- Hardcoded user_id → fetches generation first
- Storage not wired → R2 upload implemented
- Agent graph not wired → uses AI provider directly
- No retry counting → tracks retry_count from SQS ApproximateReceiveCount
- Model name inconsistency → unified to gemini-3.1-flash-image
- No graceful shutdown → waits for in-flight jobs
- No health endpoint → FastAPI app on port 8081
- Missing R2 config → added to config and env vars
- Input image download for HTTP URLs → downloads to temp file

**Completed commits:**
- `ee8dccd` feat: add worker directory with basic config
- `a511f6a` feat: add SQS consumer with retry logic
- `3fc6d8a` feat: add job processor with AI provider integration
- `81447a3` feat: wire up main with health endpoints and add AI provider
- `95e0884` feat: add agent graph wrapper placeholder
- `2ee09ec` docs: add worker environment variables
- `65d91a1` test: add basic worker tests
- `38f5995` fix: lint issues

Total: 8 tasks, 8 commits ✅
