from __future__ import annotations

from runtimes.agentcore_img2img.app.health import get_health_status


def test_health_ok() -> None:
    status = get_health_status(dependency_ok=True)
    assert status.status == "Healthy"
    assert status.dependency_status == "ok"


def test_health_degraded() -> None:
    status = get_health_status(dependency_ok=False)
    assert status.status == "Degraded"
    assert status.dependency_status == "dependency_error"
