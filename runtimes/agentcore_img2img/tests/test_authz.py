from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from runtimes.agentcore_img2img.app.authz import require_user_context
from runtimes.agentcore_img2img.app.policy import RuntimePolicy


def _request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "path": "/invocations",
        "raw_path": b"/invocations",
        "query_string": b"",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_require_user_context_from_headers() -> None:
    req = _request({"x-user-id": "user-123"})
    ctx = require_user_context(req)
    assert ctx.user_id == "user-123"


def test_require_user_context_denies_when_missing() -> None:
    req = _request({})
    with pytest.raises(HTTPException):
        require_user_context(req)


def test_policy_denies_disallowed_domain() -> None:
    policy = RuntimePolicy(allowed_input_domains={"allowed.example.com"})
    req = _request({"x-user-id": "user-123"})
    ctx = require_user_context(req)

    with pytest.raises(HTTPException):
        policy.validate_request("https://denied.example.com/input.png", ctx)
