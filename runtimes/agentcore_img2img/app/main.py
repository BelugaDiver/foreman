from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from runtimes.agentcore_img2img.app.contracts import RuntimeInvocationRequest
from runtimes.agentcore_img2img.app.graph import RuntimeGraphAdapter
from runtimes.agentcore_img2img.app import handlers
from runtimes.agentcore_img2img.app.health import get_health_status
from runtimes.agentcore_img2img.app.policy import RuntimePolicy

app = FastAPI(title="agentcore-img2img-runtime", version="0.1.0")


@app.get("/ping")
def ping() -> dict[str, str]:
    status = get_health_status(dependency_ok=True)
    return {
        "status": status.status,
        "dependency_status": status.dependency_status,
    }


@app.post("/invocations")
async def invocations(request: Request) -> dict[str, object]:
    try:
        payload = RuntimeInvocationRequest.model_validate(await request.json())
    except Exception as exc:
        raise HTTPException(status_code=422, detail="invalid invocation payload") from exc

    response = handlers.process_invocation(
        request,
        payload,
        graph=RuntimeGraphAdapter(),
        policy=RuntimePolicy(),
    )
    return response.model_dump(mode="json")
