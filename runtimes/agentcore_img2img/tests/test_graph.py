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
    return RewriteResult(
        positive_prompt=prompt,
        negative_prompt="ugly, deformed",
        elements=["sofa → linen sectional"],
        model_id="google.gemma-3-12b-it",
        latency_ms=100,
    )


def _make_verify_result(score: float = 0.9) -> VerificationResult:
    pa = min(10, max(1, round(score * 9 + 1)))
    return VerificationResult(
        prompt_alignment=pa,
        structural_fidelity=pa,
        composite_score=(pa - 1) / 9.0,
        description="Looks good overall.",
        model_id="google.gemma-3-12b-it",
        latency_ms=50,
        parse_failed=False,
    )


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


def _make_http_response(jpeg_bytes: bytes) -> MagicMock:
    mock = MagicMock()
    mock.content = jpeg_bytes
    mock.headers = {"content-type": "image/jpeg"}
    mock.raise_for_status = MagicMock()
    return mock


# ─── Tests ──────────────────────────────────────────────────────────────────


async def test_successful_run_returns_output_image_bytes(monkeypatch) -> None:
    """Happy path: all stages succeed → output_image_bytes and description present."""
    img_bytes = _make_jpeg_bytes()

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result("enriched room prompt"))), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=AsyncMock(return_value=_make_gen_result(success=True))), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=AsyncMock(return_value=_make_verify_result(0.9))), \
         patch("runtimes.agentcore_img2img.app.graph.describe_generation", new=AsyncMock(return_value="The sofa should be replaced.")):

        result = await run_graph(
            generation_id="gen-1",
            prompt="a bright room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    assert result["output_image_bytes"] is not None
    assert result["generated_image_description"] == "The sofa should be replaced."
    assert result["output_image_url"] is None
    assert result["model_used"] is not None


async def test_sd_failure_returns_null_bytes_with_description(monkeypatch) -> None:
    """Stage 2 failure → output_image_bytes=None, description falls back to positive_prompt."""
    img_bytes = _make_jpeg_bytes()

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result("my enriched prompt"))), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=AsyncMock(return_value=_make_gen_result(success=False))):

        result = await run_graph(
            generation_id="gen-2",
            prompt="a room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    assert result["output_image_bytes"] is None
    assert result["generated_image_description"] == "my enriched prompt"


async def test_missing_input_image_url_raises_before_any_model_call(monkeypatch) -> None:
    """Missing input_image_url → ValueError raised before any model is called."""
    rewrite_mock = AsyncMock(return_value=_make_rewrite_result())

    with patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=rewrite_mock):
        with pytest.raises(ValueError, match="input_image_url"):
            await run_graph(
                generation_id="gen-3",
                prompt="a room",
                input_image_url=None,
                style_id=None,
            )

    rewrite_mock.assert_not_called()


async def test_stage1_failure_propagates_exception(monkeypatch) -> None:
    """Stage 1 error propagates — no partial result returned."""
    img_bytes = _make_jpeg_bytes()

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(side_effect=RuntimeError("Nova failed"))):

        with pytest.raises(RuntimeError, match="Nova failed"):
            await run_graph(
                generation_id="gen-4",
                prompt="a room",
                input_image_url="https://cdn.example.com/input.jpg",
                style_id=None,
            )


async def test_otel_spans_emitted_for_all_stages(monkeypatch) -> None:
    """OTEL spans emitted for all stages: rewrite, generate, verify, describe."""
    img_bytes = _make_jpeg_bytes()

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    import runtimes.agentcore_img2img.app.graph as graph_mod
    original_tracer = graph_mod.tracer

    try:
        graph_mod.tracer = provider.get_tracer(__name__)

        with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
             patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
             patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result())), \
             patch("runtimes.agentcore_img2img.app.graph.generate_image", new=AsyncMock(return_value=_make_gen_result(success=True))), \
             patch("runtimes.agentcore_img2img.app.graph.verify_image", new=AsyncMock(return_value=_make_verify_result(0.9))), \
             patch("runtimes.agentcore_img2img.app.graph.describe_generation", new=AsyncMock(return_value="description")):

            await run_graph(
                generation_id="gen-otel",
                prompt="a room",
                input_image_url="https://cdn.example.com/input.jpg",
                style_id=None,
            )
    finally:
        graph_mod.tracer = original_tracer

    span_names = [s.name for s in exporter.get_finished_spans()]
    assert "stage1.rewrite_prompt" in span_names
    assert "stage2.generate_image" in span_names
    assert "stage_v.verify_image" in span_names
    assert "stage3.describe_generation" in span_names


async def test_stage2_called_with_enriched_prompt(monkeypatch) -> None:
    """Stage 2 receives the positive_prompt from Stage 1, not the original."""
    img_bytes = _make_jpeg_bytes()
    gen_mock = AsyncMock(return_value=_make_gen_result(success=True))

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result("the enriched prompt"))), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=gen_mock), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=AsyncMock(return_value=_make_verify_result(0.9))), \
         patch("runtimes.agentcore_img2img.app.graph.describe_generation", new=AsyncMock(return_value="desc")):

        await run_graph(
            generation_id="gen-5",
            prompt="original prompt",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    call_kwargs = gen_mock.call_args.kwargs
    assert call_kwargs["enriched_prompt"] == "the enriched prompt"


async def test_loop_exits_early_when_threshold_met(monkeypatch) -> None:
    """Loop exits after first iteration when verify score >= threshold (0.75)."""
    img_bytes = _make_jpeg_bytes()
    rewrite_mock = AsyncMock(return_value=_make_rewrite_result())
    gen_mock = AsyncMock(return_value=_make_gen_result(success=True))
    # score 0.9 ≥ default threshold 0.75 → should exit after iteration 0
    verify_mock = AsyncMock(return_value=_make_verify_result(0.9))

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=rewrite_mock), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=gen_mock), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=verify_mock), \
         patch("runtimes.agentcore_img2img.app.graph.describe_generation", new=AsyncMock(return_value="desc")):

        await run_graph(
            generation_id="gen-loop-early",
            prompt="a room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    # rewrite called once (initial only), generate and verify each called once
    assert rewrite_mock.call_count == 1
    assert gen_mock.call_count == 1
    assert verify_mock.call_count == 1


async def test_loop_retries_with_correction_context_on_low_score(monkeypatch) -> None:
    """Low verify score triggers Stage 1 retry with correction_context."""
    img_bytes = _make_jpeg_bytes()
    rewrite_mock = AsyncMock(return_value=_make_rewrite_result())
    gen_mock = AsyncMock(return_value=_make_gen_result(success=True))
    # First score below threshold, second above → two iterations
    low_result = _make_verify_result(0.4)
    low_result.description  # already set via helper
    verify_mock = AsyncMock(side_effect=[low_result, _make_verify_result(0.9)])

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=rewrite_mock), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=gen_mock), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=verify_mock), \
         patch("runtimes.agentcore_img2img.app.graph.describe_generation", new=AsyncMock(return_value="desc")):

        await run_graph(
            generation_id="gen-loop-retry",
            prompt="a room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    assert rewrite_mock.call_count == 2
    assert gen_mock.call_count == 2
    assert verify_mock.call_count == 2
    # Second rewrite call must have correction_context set
    second_call_kwargs = rewrite_mock.call_args_list[1].kwargs
    assert second_call_kwargs["correction_context"] == low_result.description


async def test_loop_returns_best_candidate_not_last(monkeypatch) -> None:
    """Best image by score is returned even if last iteration scores lower."""
    img_bytes_1 = _make_jpeg_bytes(color="blue")
    img_bytes_2 = _make_jpeg_bytes(color="red")

    gen_result_1 = GenerationResult(
        image_bytes=img_bytes_1, image_b64=_b64(img_bytes_1),
        finish_reason=None, seed=1, model_id="sd", latency_ms=100,
    )
    gen_result_2 = GenerationResult(
        image_bytes=img_bytes_2, image_b64=_b64(img_bytes_2),
        finish_reason=None, seed=2, model_id="sd", latency_ms=100,
    )

    img_bytes = _make_jpeg_bytes()
    high_score = _make_verify_result(0.85)
    low_score = _make_verify_result(0.3)

    with patch("runtimes.agentcore_img2img.app.graph.httpx.get", return_value=_make_http_response(img_bytes)), \
         patch("runtimes.agentcore_img2img.app.graph._resize_image", return_value=(img_bytes, "jpeg")), \
         patch("runtimes.agentcore_img2img.app.graph.rewrite_prompt", new=AsyncMock(return_value=_make_rewrite_result())), \
         patch("runtimes.agentcore_img2img.app.graph.generate_image", new=AsyncMock(side_effect=[gen_result_1, gen_result_2])), \
         patch("runtimes.agentcore_img2img.app.graph.verify_image", new=AsyncMock(side_effect=[high_score, low_score])), \
         patch("runtimes.agentcore_img2img.app.graph.describe_generation", new=AsyncMock(return_value="desc")) as describe_mock:

        await run_graph(
            generation_id="gen-best",
            prompt="a room",
            input_image_url="https://cdn.example.com/input.jpg",
            style_id=None,
        )

    # describe_generation should have been called with gen_result_1's bytes (higher score)
    describe_call_kwargs = describe_mock.call_args.kwargs
    assert describe_call_kwargs["generated_image_b64"] == gen_result_1.image_b64


