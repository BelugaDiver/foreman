from __future__ import annotations

import os
from urllib.parse import urlparse


class RuntimePolicy:
    """Runtime allow/deny policy for outbound URL constraints."""

    def __init__(self, allowed_input_domains: set[str] | None = None) -> None:
        self.allowed_input_domains = allowed_input_domains or self._load_allowed_domains()

    @staticmethod
    def _load_allowed_domains() -> set[str]:
        configured = os.getenv("RUNTIME_ALLOWED_INPUT_DOMAINS", "")
        return {d.strip().lower() for d in configured.split(",") if d.strip()}

    def validate_request(self, input_image_url: str) -> None:
        parsed = urlparse(input_image_url)
        host = (parsed.hostname or "").lower()
        if not host:
            raise ValueError("invalid input_image_url: missing host")
        if self.allowed_input_domains and host not in self.allowed_input_domains:
            raise ValueError(f"input_image_url host '{host}' is not permitted by runtime policy")
