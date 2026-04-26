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

    NOTE: This class is not yet integrated into the active processing pipeline.
    The active path is worker/providers/vertex.py (GeminiProvider).
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

        raise NotImplementedError(
            "AgentGraph.run() is not yet implemented. "
            "Integrate your custom agent pipeline here."
        )
