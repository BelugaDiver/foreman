"""AgentCore Img2Img Runtime — entry point.

Run locally (from repo root):
    python runtimes/agentcore_img2img/app/main.py

Deployed: app/*.py are copied flat to the ZIP root.
Flat imports (graph, contracts, policy) work in both cases because Python
adds the script's directory to sys.path when running directly.
"""

from __future__ import annotations

import logging
import os
import sys

# Configure root logger to stdout before any module imports so all loggers
# (including graph.py, policy.py) emit to the container's stdout stream,
# which CloudWatch captures via /aws/bedrock-agentcore/runtimes/{agent_id}.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)

# Safe default so the runtime works even without explicit env config.
# Use the direct regional model ID to avoid the Marketplace subscription
# required by the cross-region inference profile prefix "global.".
os.environ.setdefault("RUNTIME_STRANDS_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0")

from bedrock_agentcore import BedrockAgentCoreApp  # provided by amazon-bedrock-agentcore
from contracts import RuntimeInvocationRequest  # siblings in app/ or ZIP root
from graph import run_graph
from policy import RuntimePolicy

logger = logging.getLogger(__name__)

_policy = RuntimePolicy()
app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    """Process one image generation invocation."""
    try:
        req = RuntimeInvocationRequest.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"invalid payload: {exc}") from exc

    if req.input_image_url:
        try:
            _policy.validate_request(str(req.input_image_url))
        except ValueError as exc:
            raise PermissionError(str(exc)) from exc

    return run_graph(
        generation_id=req.generation_id,
        prompt=req.prompt,
        input_image_url=str(req.input_image_url) if req.input_image_url else None,
        style_id=req.style_id,
    )


if __name__ == "__main__":
    app.run()
