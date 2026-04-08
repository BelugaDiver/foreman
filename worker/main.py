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
