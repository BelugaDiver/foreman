from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class UserContext:
    """Caller user/tenant context required by runtime authorization."""

    user_id: str


def require_user_context(request: Request) -> UserContext:
    """Resolve required user context from invocation headers."""

    user_id = (
        request.headers.get("x-user-id")
        or request.headers.get("x-runtime-user-id")
        or request.headers.get("x-foreman-user-id")
    )
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="missing required user context",
        )
    return UserContext(user_id=user_id)
