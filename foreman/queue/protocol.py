"""Queue protocol for abstracting queue implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class QueueMessage:
    """Represents a message to be sent to the queue."""

    body: dict[str, Any]
    message_attributes: dict[str, str] | None = None


class QueueProtocol(ABC):
    """Abstract queue interface."""

    @abstractmethod
    async def publish(self, message: QueueMessage) -> str | None:
        """Publish a message to the queue.

        Args:
            message: The message to publish

        Returns:
            The message ID from the queue service, or None if queue is disabled
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close any connections."""
        pass
