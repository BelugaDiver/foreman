from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import HTTPException, status

from runtimes.agentcore_img2img.app.authz import UserContext


class RuntimePolicy:
    """Runtime allow/deny policy for tenant and outbound URL constraints."""

    def __init__(self, allowed_input_domains: set[str] | None = None) -> None:
        self.allowed_input_domains = allowed_input_domains or self._load_allowed_domains()

    @staticmethod
    def _load_allowed_domains() -> set[str]:
        configured = os.getenv("RUNTIME_ALLOWED_INPUT_DOMAINS", "")
        return {d.strip().lower() for d in configured.split(",") if d.strip()}

    def validate_request(self, input_image_url: str, user_context: UserContext) -> None:
        if not user_context.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="missing user context",
            )

        parsed = urlparse(input_image_url)
        host = (parsed.hostname or "").lower()
        if not host:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid input_image_url host",
            )

        if self.allowed_input_domains and host not in self.allowed_input_domains:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="input_image_url host is not allowed by runtime policy",
            )
