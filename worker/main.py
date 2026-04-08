"""Worker entry point."""

import asyncio
import logging
import os
import signal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from uvicorn import Config, Server

from foreman.db import Database
from foreman.queue.settings import SQSSettings
from foreman.telemetry import setup_telemetry
from worker.config import get_worker_config
from worker.consumer import SQSConsumer
from worker.processor import JobProcessor
from worker.providers import get_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("worker.main")

health_app = FastAPI(title="worker-health")

_db_instance: Database | None = None


@health_app.get("/health")
async def health():
    """Liveness check."""
    return {"status": "ok"}


@health_app.get("/ready")
async def ready():
    """Readiness check - verifies DB connectivity."""
    global _db_instance
    if _db_instance is None:
        return JSONResponse({"status": "not ready", "database": "not initialized"}, status_code=503)
    try:
        await _db_instance.execute("SELECT 1")
        return {"status": "ready", "database": "connected"}
    except Exception:
        return JSONResponse({"status": "not ready", "database": "disconnected"}, status_code=503)


async def main():
    global _db_instance

    setup_telemetry(
        service_name="foreman-worker",
        otlp_endpoint=os.getenv("OTLP_ENDPOINT"),
    )
    logger.info("Telemetry initialized")

    config = get_worker_config()
    logger.info("Starting worker")

    sqs_settings = SQSSettings.from_env()
    if not sqs_settings.is_configured:
        logger.error("SQS not configured. Set SQS_QUEUE_URL")
        return

    db = Database.from_env()
    await db.connect()
    _db_instance = db
    logger.info("Database connected")

    ai_provider = get_provider(
        provider_type=config.ai_provider,
        project_id=config.google_project_id,
        location=config.google_location,
        image_model=config.gemini_image_model,
        enhancement_model=config.gemini_enhancement_model,
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
    )

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
        await consumer.stop(timeout=60.0)

        health_server.should_exit = True
        await health_task

        _db_instance = None
        await db.disconnect()
        logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
