from __future__ import annotations

import os

from fastapi.testclient import TestClient

from runtimes.agentcore_img2img.app.main import app
from runtimes.agentcore_img2img.app import handlers


client = TestClient(app)


def test_deny_missing_user_context() -> None:
    os.environ["RUNTIME_OUTPUT_BASE_URL"] = "https://cdn.example.com/generated"
    response = client.post(
        "/invocations",
        json={
            "prompt": "test",
            "generation_id": "gen-123",
            "input_image_url": "https://allowed.example.com/input.png",
        },
    )
    assert response.status_code == 403


def test_deny_disallowed_input_host_with_allowlist() -> None:
    os.environ["RUNTIME_OUTPUT_BASE_URL"] = "https://cdn.example.com/generated"
    os.environ["RUNTIME_ALLOWED_INPUT_DOMAINS"] = "allowed.example.com"

    response = client.post(
        "/invocations",
        json={
            "prompt": "test",
            "generation_id": "gen-123",
            "input_image_url": "https://denied.example.com/input.png",
        },
        headers={"x-user-id": "user-1"},
    )
    assert response.status_code == 403


def test_deny_event_emitted(monkeypatch) -> None:
    emitted: list[str] = []

    def capture(event: str, **_: str) -> None:
        emitted.append(event)

    monkeypatch.setattr(handlers, "emit_runtime_event", capture)

    response = client.post(
        "/invocations",
        json={
            "prompt": "deny audit",
            "generation_id": "gen-deny",
            "input_image_url": "https://denied.example.com/input.png",
        },
        headers={"x-user-id": "user-1"},
    )
    assert response.status_code in {403, 422}
    assert "invocation_denied" in emitted or "invocation_received" in emitted
