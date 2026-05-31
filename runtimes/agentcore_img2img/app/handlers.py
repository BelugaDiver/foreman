from __future__ import annotations

from fastapi import HTTPException, Request, status

from runtimes.agentcore_img2img.app.authz import require_user_context
from runtimes.agentcore_img2img.app.contracts import RuntimeInvocationRequest, RuntimeInvocationResponse
from runtimes.agentcore_img2img.app.graph import RuntimeGraphAdapter
from runtimes.agentcore_img2img.app.policy import RuntimePolicy
from runtimes.agentcore_img2img.app.telemetry import emit_runtime_event


def _resolve_runtime_session_id(request: Request, payload: RuntimeInvocationRequest) -> str | None:
    header_session_id = request.headers.get("x-amzn-bedrock-agentcore-runtime-session-id")
    return payload.runtime_session_id or header_session_id


def process_invocation(
    request: Request,
    payload: RuntimeInvocationRequest,
    *,
    graph: RuntimeGraphAdapter,
    policy: RuntimePolicy,
) -> RuntimeInvocationResponse:
    user_context = require_user_context(request)
    runtime_session_id = _resolve_runtime_session_id(request, payload)

    emit_runtime_event(
        "invocation_received",
        generation_id=payload.generation_id,
        runtime_session_id=runtime_session_id,
        user_id=user_context.user_id,
    )

    try:
        policy.validate_request(str(payload.input_image_url), user_context)
    except HTTPException:
        emit_runtime_event(
            "invocation_denied",
            generation_id=payload.generation_id,
            runtime_session_id=runtime_session_id,
            user_id=user_context.user_id,
            reason="policy_denied",
        )
        raise

    try:
        result = graph.run(
            generation_id=payload.generation_id,
            prompt=payload.prompt,
            input_image_url=str(payload.input_image_url),
            style_id=payload.style_id,
        )
    except ValueError as exc:
        emit_runtime_event(
            "invocation_failed",
            generation_id=payload.generation_id,
            runtime_session_id=runtime_session_id,
            user_id=user_context.user_id,
            reason="graph_error",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    response = RuntimeInvocationResponse(
        output_image_url=result.output_image_url,
        generated_image_description=result.generated_image_description,
        model_used=result.model_used,
    )

    emit_runtime_event(
        "invocation_completed",
        generation_id=payload.generation_id,
        runtime_session_id=runtime_session_id,
        user_id=user_context.user_id,
        output_image_url=str(response.output_image_url),
    )
    return response
