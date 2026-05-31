from __future__ import annotations

import time

from fastapi import HTTPException
from fastapi.testclient import TestClient

from runtimes.agentcore_img2img.app.main import app


client = TestClient(app)


def test_recovery_after_transient_runtime_failure(monkeypatch) -> None:
    calls = {"count": 0}

    from runtimes.agentcore_img2img.app import handlers

    original = handlers.process_invocation

    def flaky(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPException(status_code=500, detail="transient")
        return original(*args, **kwargs)

    monkeypatch.setattr(handlers, "process_invocation", flaky)

    payload = {
        "prompt": "retry",
        "generation_id": "gen-recover",
        "input_image_url": "https://allowed.example.com/input.png",
    }
    headers = {"x-user-id": "user-1"}

    first = client.post("/invocations", json=payload, headers=headers)
    assert first.status_code == 500

    second = client.post("/invocations", json=payload, headers=headers)
    assert second.status_code == 200


def test_ping_reports_health() -> None:
    started = time.monotonic()
    response = client.get("/ping")
    elapsed = time.monotonic() - started
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"Healthy", "Degraded"}
    assert elapsed < 300
