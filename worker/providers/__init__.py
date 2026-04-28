"""AI provider implementations."""

from worker.providers.vertex import GeminiProvider

__all__ = ["GeminiProvider", "get_provider"]


def get_provider(provider_type: str = "vertex", **kwargs):
    """Factory to get AI provider."""
    if provider_type == "vertex":
        return GeminiProvider(**kwargs)
    raise ValueError(f"Unknown provider: {provider_type}")
