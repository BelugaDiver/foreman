from __future__ import annotations

import os
import time

from fastapi.testclient import TestClient

from runtimes.agentcore_img2img.app.main import app
from runtimes.agentcore_img2img.app import handlers


client = TestClient(app)


def test_invocation_contract_success_metadata_only() -> None:
    os.environ["RUNTIME_OUTPUT_BASE_URL"] = "https://cdn.example.com/generated"

    start = time.monotonic()
    response = client.post(
        "/invocations",
        json={
            "prompt": "a stylized portrait",
            "generation_id": "gen-abc",
            "input_image_url": "https://allowed.example.com/input.png",
            "style_id": "noir",
            "runtime_session_id": "proj-gen-abc",
        },
        headers={"x-user-id": "user-123"},
    )
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    body = response.json()
    assert body["output_image_url"].startswith("https://")
    assert "binary_image" not in body
    assert "image_bytes" not in body
    assert elapsed < 60


def test_audit_events_emitted_for_success(monkeypatch) -> None:
    os.environ["RUNTIME_OUTPUT_BASE_URL"] = "https://cdn.example.com/generated"
    emitted: list[dict[str, str]] = []

    def capture(event: str, **fields: str) -> None:
        emitted.append({"event": event, **{k: str(v) for k, v in fields.items() if v is not None}})

    monkeypatch.setattr(handlers, "emit_runtime_event", capture)

    response = client.post(
        "/invocations",
        json={
            "prompt": "audit test",
            "generation_id": "gen-audit",
            "input_image_url": "https://allowed.example.com/input.png",
        },
        headers={"x-user-id": "user-audit"},
    )
    assert response.status_code == 200

    event_names = [entry["event"] for entry in emitted]
    assert "invocation_received" in event_names
    assert "invocation_completed" in event_names

    completed = next(entry for entry in emitted if entry["event"] == "invocation_completed")
    assert completed["generation_id"] == "gen-audit"
    assert completed["user_id"] == "user-audit"


def test_invocation_contract_rejects_invalid_payload() -> None:
    response = client.post(
        "/invocations",
        json={"prompt": "missing required fields"},
        headers={"x-user-id": "user-123"},
    )
    assert response.status_code == 422
