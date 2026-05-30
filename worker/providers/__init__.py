"""AI provider implementations."""

from worker.providers.agentcore import AgentCoreProvider
from worker.providers.vertex import GeminiProvider

__all__ = ["AgentCoreProvider", "GeminiProvider", "get_provider"]


def get_provider(provider_type: str = "vertex", **kwargs):
    """Factory to get AI provider."""
    if provider_type == "vertex":
        return GeminiProvider(**kwargs)
    if provider_type == "agentcore":
        return AgentCoreProvider(**kwargs)
    raise ValueError(f"Unknown provider: {provider_type}")
