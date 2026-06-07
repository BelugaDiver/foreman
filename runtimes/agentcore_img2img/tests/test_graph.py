from __future__ import annotations

import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry import trace

from runtimes.agentcore_img2img.app.graph import run_graph
from runtimes.agentcore_img2img.app.stages.generator import GenerationResult
from runtimes.agentcore_img2img.app.stages.rewriter import RewriteResult
from runtimes.agentcore_img2img.app.stages.verifier import VerificationResult


# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_jpeg_bytes(color: str = "blue") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _make_rewrite_result(prompt: str = "enriched prompt") -> RewriteResult:
    return RewriteResult(enriched_prompt=prompt, model_id="amazon.nova-lite-v1:0", latency_ms=100)


def _make_gen_result(success: bool = True) -> GenerationResult:
    if success:
        img = _make_jpeg_bytes()
        return GenerationResult(
            image_bytes=img,
            image_b64=_b64(img),
            finish_reason=None,
            seed=42,
            model_id="us.stability.stable-image-control-structure-v1:0",
            latency_ms=500,
        )
    return GenerationResult(
        image_bytes=b"",
        image_b64="",
        finish_reason="ERROR",
        seed=0,
        model_id="us.stability.stable-image-control-structure-v1:0",
        latency_ms=100,
    )


def _make_ver_result(score: float = 0.9, parse_failed: bool = False) -> VerificationResult:
    pa = round(score * 9 + 1)
    return VerificationResult(
        prompt_alignment=pa,
        structural_fidelity=pa,
        composite_score=score,
        description="Good match",
        model_id="amazon.nova-lite-v1:0",
        latency_ms=200,
        parse_failed=parse_failed,
    )


def _make_http_response(jpeg_bytes: bytes) -> MagicMock:
    mock = MagicMock()
    mock.content = jpeg_bytes
    mock.headers = {"content-type": "image/jpeg"}
    mock.raise_for_status = MagicMock()
    return mock


def _patch_env(monkeypatch):
    monkeypatch.setenv("RUNTIME_OUTPUT_BASE_URL", "https://cdn.example.com/out")
    monkeypatch.setenv("VERIFICATION_MAX_ITERATIONS", "3")
    monkeypatch.setenv("VERIFICATION_ALIGNMENT_THRESHOLD", "0.75")
    monkeypatch.setenv("VERIFICATION_TIME_BUDGET_SECONDS", "120")
    monkeypatch.setenv("VERIFICATION_ITER_ESTIMATE_SECONDS", "30")


# ─── Tests ──────────────────────────────────────────────────────────────────


async def test_threshold_met_first_iteration_returns_output_image_bytes(
    monkeypatch,
) -> None:
    """End-to-end: threshold met on first iteration → output_image_bytes present."""
    _patch_env(monkeypatch)
    img_bytes = _make_jpeg_bytes()

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result())), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=AsyncMock(return_value=_make_gen_result(success=True))), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=AsyncMock(return_value=_make_ver_result(score=0.9))):

        result = await run_graph(
            generation_id="gen-1",
            prompt="a bright room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    assert result["output_image_bytes"] is not None
    assert result["generated_image_description"] == "Good match"
    assert "gen-1" in result["output_image_url"]


async def test_loop_exits_after_max_iterations_returns_best_candidate(
    monkeypatch,
) -> None:
    """Loop exits after max_iterations → best-scoring candidate returned, not error."""
    _patch_env(monkeypatch)
    monkeypatch.setenv("VERIFICATION_MAX_ITERATIONS", "2")
    monkeypatch.setenv("VERIFICATION_ALIGNMENT_THRESHOLD", "0.99")  # never met
    img_bytes = _make_jpeg_bytes()

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result())), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=AsyncMock(return_value=_make_gen_result(success=True))), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=AsyncMock(return_value=_make_ver_result(score=0.5))):

        result = await run_graph(
            generation_id="gen-2",
            prompt="a room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    assert result["output_image_bytes"] is not None
    assert result.get("error") is None


async def test_loop_exits_on_time_budget_precheck_returns_best_candidate(
    monkeypatch,
) -> None:
    """Loop exits on time budget pre-check → best candidate returned."""
    _patch_env(monkeypatch)
    # Set budget < estimate: will exit before iteration 1
    monkeypatch.setenv("VERIFICATION_TIME_BUDGET_SECONDS", "10")
    monkeypatch.setenv("VERIFICATION_ITER_ESTIMATE_SECONDS", "100")  # estimate > budget
    img_bytes = _make_jpeg_bytes()

    gen_mock = AsyncMock(return_value=_make_gen_result(success=True))
    ver_mock = AsyncMock(return_value=_make_ver_result(score=0.5))

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result())), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=gen_mock), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=ver_mock):

        result = await run_graph(
            generation_id="gen-3",
            prompt="a room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    # Generation should never be called
    gen_mock.assert_not_called()
    # Falls back to enriched prompt as description since no SD succeeded
    assert result["output_image_bytes"] is None


async def test_sd_failure_all_iterations_returns_description_from_stage1(
    monkeypatch,
) -> None:
    """SD failure on all iterations → output_image_bytes=None, description from Stage 1."""
    _patch_env(monkeypatch)
    monkeypatch.setenv("VERIFICATION_MAX_ITERATIONS", "2")
    img_bytes = _make_jpeg_bytes()

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result("my enriched prompt"))), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=AsyncMock(return_value=_make_gen_result(success=False))), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=AsyncMock(return_value=_make_ver_result())):

        result = await run_graph(
            generation_id="gen-4",
            prompt="a room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    assert result["output_image_bytes"] is None
    assert result["generated_image_description"] == "my enriched prompt"


async def test_no_sd_generation_ever_succeeded_returns_description_only_no_exception(
    monkeypatch,
) -> None:
    """FR-020: all SD calls fail before any result → description-only, no unhandled exception."""
    _patch_env(monkeypatch)
    img_bytes = _make_jpeg_bytes()

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result("fallback desc"))), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=AsyncMock(return_value=_make_gen_result(success=False))), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=AsyncMock(return_value=_make_ver_result())):

        result = await run_graph(
            generation_id="gen-5",
            prompt="a room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    assert result["output_image_bytes"] is None
    assert result["generated_image_description"] == "fallback desc"
    assert result["output_image_url"] is not None


async def test_stage1_failure_propagates_exception(monkeypatch) -> None:
    """Stage 1 error propagates — no partial result returned."""
    _patch_env(monkeypatch)
    img_bytes = _make_jpeg_bytes()

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(side_effect=RuntimeError("Nova Lite failed"))):

        with pytest.raises(RuntimeError, match="Nova Lite failed"):
            await run_graph(
                generation_id="gen-6",
                prompt="a room",
                input_image_url="https://cdn.example.com/input.jpg",
                style_id=None,
            )


async def test_verification_parse_failure_fail_open_exits_loop_returns_result(
    monkeypatch,
) -> None:
    """Verification fail-open (parse failure) → exits loop, returns current result."""
    _patch_env(monkeypatch)
    img_bytes = _make_jpeg_bytes()
    ver_mock = AsyncMock(return_value=_make_ver_result(score=1.0, parse_failed=True))

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result())), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=AsyncMock(return_value=_make_gen_result(success=True))), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=ver_mock):

        result = await run_graph(
            generation_id="gen-7",
            prompt="a room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    # Only one verification call (fail-open exit)
    assert ver_mock.call_count == 1
    assert result["output_image_bytes"] is not None


async def test_missing_input_image_url_raises_before_any_model_call(
    monkeypatch,
) -> None:
    """Missing input_image_url → ValueError raised before any model is called."""
    _patch_env(monkeypatch)

    rewrite_mock = AsyncMock(return_value=_make_rewrite_result())

    with patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=rewrite_mock):
        with pytest.raises(ValueError, match="input_image_url"):
            await run_graph(
                generation_id="gen-8",
                prompt="a room",
                input_image_url=None,
                style_id=None,
            )

    rewrite_mock.assert_not_called()


async def test_missing_runtime_output_base_url_raises(monkeypatch) -> None:
    """Missing RUNTIME_OUTPUT_BASE_URL → ValueError."""
    monkeypatch.delenv("RUNTIME_OUTPUT_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="RUNTIME_OUTPUT_BASE_URL"):
        await run_graph(
            generation_id="gen-9",
            prompt="a room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )


async def test_otel_spans_emitted_for_all_three_stages(monkeypatch) -> None:
    """FR-012 / SC-006: OTEL spans emitted with generation_id, model_id, latency_ms for all stages."""
    _patch_env(monkeypatch)
    img_bytes = _make_jpeg_bytes()

    # Install an in-memory tracer
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    original_provider = trace.get_tracer_provider()

    import runtimes.agentcore_img2img.app.graph as graph_mod
    original_tracer = graph_mod.tracer

    try:
        graph_mod.tracer = provider.get_tracer(__name__)

        with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
             patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
             patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result())), \
             patch("runtimes.agentcore_img2img.app.graph.generate_image", new=AsyncMock(return_value=_make_gen_result(success=True))), \
             patch("runtimes.agentcore_img2img.app.graph.verify_image", new=AsyncMock(return_value=_make_ver_result(score=0.9))):

            await run_graph(
                generation_id="gen-otel",
                prompt="a room",
                input_image_url="https://cdn.example.com/input.jpg",
                style_id=None,
            )
    finally:
        graph_mod.tracer = original_tracer

    spans = exporter.get_finished_spans()
    span_names = [s.name for s in spans]

    assert "stage1.rewrite_prompt" in span_names
    assert "stage2.generate_image" in span_names
    assert "stage3.verify_image" in span_names

    for span in spans:
        if span.name in ("stage1.rewrite_prompt", "stage2.generate_image", "stage3.verify_image"):
            attrs = span.attributes
            assert "generation_id" in attrs
            assert "model_id" in attrs
            assert "latency_ms" in attrs


async def test_exit_reason_logged_for_threshold_met(monkeypatch, caplog) -> None:
    """FR-022 / SC-011: exit_reason logged for threshold_met exit."""
    import logging
    _patch_env(monkeypatch)
    img_bytes = _make_jpeg_bytes()

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result())), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=AsyncMock(return_value=_make_gen_result(success=True))), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=AsyncMock(return_value=_make_ver_result(score=0.9))), \
         caplog.at_level(logging.INFO, logger="runtimes.agentcore_img2img.app.graph"):

        await run_graph(
            generation_id="gen-exit",
            prompt="a room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    combined = " ".join(caplog.messages)
    assert "threshold_met" in combined
    assert "exit_reason" in combined
