"""Worker entry point."""

import asyncio
import os
import signal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from uvicorn import Config, Server

from foreman.db import Database, sql
from foreman.logging_config import configure_logging, get_logger
from foreman.queue.settings import SQSSettings
from foreman.telemetry import setup_telemetry
from worker.config import get_worker_config
from worker.consumer import SQSConsumer
from worker.processor import JobProcessor
from worker.providers import get_provider

logger = get_logger("worker.main")

health_app = FastAPI(title="worker-health")

_db_instance: Database | None = None
_consumer_instance: SQSConsumer | None = None


@health_app.get("/health")
async def health():
    """Liveness check."""
    return {"status": "ok"}


@health_app.get("/ready")
async def ready():
    """Readiness check - verifies DB connectivity and consumer status."""
    global _db_instance, _consumer_instance

    status = "ready"
    checks = {}

    # DB Check
    if _db_instance is None:
        status = "not ready"
        checks["database"] = "not initialized"
    else:
        try:
            await _db_instance.execute(sql("SELECT 1"))
            checks["database"] = "connected"
        except Exception:
            status = "not ready"
            checks["database"] = "disconnected"

    # Consumer Check
    if _consumer_instance is None:
        status = "not ready"
        checks["consumer"] = "not initialized"
    elif not _consumer_instance.is_ready():
        status = "not ready"
        checks["consumer"] = "stopped"
    else:
        checks["consumer"] = "running"

    if status != "ready":
        return JSONResponse({"status": status, **checks}, status_code=503)

    return {"status": status, **checks}


async def main():
    global _db_instance, _consumer_instance

    # Initialize logging centrally
    configure_logging()

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"
    setup_telemetry(
        service_name="foreman-worker",
        otlp_endpoint=otlp_endpoint,
        insecure=insecure,
    )
    logger.info("Telemetry initialized")

    config = get_worker_config()
    logger.info("Starting worker")

    sqs_settings = SQSSettings.from_env()
    if not sqs_settings.is_configured:
        logger.error("SQS not configured. Set SQS_QUEUE_URL")
        return

    db = Database.from_env()
    await db.startup()
    _db_instance = db
    logger.info("Database connected")

    ai_provider = get_provider(
        provider_type=config.ai_provider,
        project_id=config.google_project_id,
        location=config.google_location,
        image_model=config.gemini_image_model,
        enhancement_model=config.gemini_enhancement_model,
        allowed_image_domains=config.get_allowed_image_domains(),
    )

    health_server = Server(Config(app=health_app, host="0.0.0.0", port=8081, log_level="warning"))
    health_task = asyncio.create_task(health_server.serve())
    logger.info("Health server started on port 8081")

    processor = JobProcessor(db, config, ai_provider)

    consumer = SQSConsumer(
        queue_url=sqs_settings.queue_url,
        process_fn=processor.process,
        concurrency=config.concurrency,
        max_retries=config.max_retries,
        poll_interval=config.poll_interval,
        visibility_timeout=config.visibility_timeout,
    )
    _consumer_instance = consumer

    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating shutdown...")
        shutdown_event.set()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: shutdown_event.set())
    except RuntimeError:
        logger.debug("No running loop, signal handlers not registered")

    async def run_consumer():
        await consumer.start()

    async def wait_for_shutdown():
        await shutdown_event.wait()
        await consumer.stop(timeout=60.0)

    try:
        await asyncio.gather(run_consumer(), wait_for_shutdown(), return_exceptions=False)
    except asyncio.CancelledError:
        logger.info("Consumer cancelled")
    finally:
        await consumer.stop(timeout=60.0)
        health_server.should_exit = True
        await health_task

        _db_instance = None
        await db.shutdown()
        logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
