# Implementation Plan: Runtime Image Generation Pipeline

**Branch**: `main` | **Date**: 2026-06-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/004-runtime-img-generation/spec.md`

## Summary

Extend `runtimes/agentcore_img2img` into a fully-featured agent harness with a three-stage pipeline: (1) prompt rewriting via a multimodal model (Google Gemma / equivalent via Bedrock), (2) Stable Diffusion + ControlNet image generation using the enriched prompt and input image, and (3) a verification loop that re-scores the output image against the original prompt and input image using a composite alignment score, retrying with refined prompts up to a wall-clock budget and iteration cap. The runtime returns base64-encoded image bytes to the worker (Option B), which handles storage. The worker's `AgentCoreProvider` is updated to decode and upload these bytes before writing `output_image_url`.

## Technical Context

**Language/Version**: Python 3.11 (runtime ZIP), Python 3.11+ (worker)
**Primary Dependencies**: `amazon-bedrock-agentcore`, `boto3`, `Pillow`, `httpx`, `pydantic` v2
**Storage**: AWS S3 / Cloudflare R2 via `StorageProtocol` (worker side); runtime has no storage dependency
**Testing**: `pytest` with `asyncio_mode = "auto"`; mocks via `monkeypatch`; 85% coverage gate
**Target Platform**: AWS Lambda / AgentCore runtime ZIP (runtime); Linux container (worker)
**Project Type**: Event-driven microservice pipeline
**Performance Goals**: End-to-end pipeline within `VERIFICATION_TIME_BUDGET_SECONDS` (default 60s); p95 first-generation <=30s
**Constraints**: AgentCore response body <= `MAX_OUTPUT_IMAGE_BYTES` (default 1 MB base64-decoded); runtime has no outbound access to Foreman API; Bedrock region = `AWS_DEFAULT_REGION`
**Scale/Scope**: Per-invocation stateless; verification loop max 3 iterations by default

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*
*Reference: `.specify/memory/constitution.md`*

- [x] **I. Layered Architecture** -- all changes are within `runtimes/` (self-contained deployable) or `worker/providers/agentcore.py`; no new Foreman API/repo/model layers are added. The runtime is an isolated module, not part of the Foreman layered stack.
- [x] **II. Raw SQL** -- no database changes in this feature; no SQL written.
- [x] **III. Async-First** -- all boto3 calls wrapped in `asyncio.to_thread()` (established pattern in `agentcore.py`); new pipeline stages follow the same pattern.
- [x] **IV. Event-Driven** -- generation dispatched by worker via `QueueProtocol` -> `AgentCoreProvider.generate()`; this feature extends the runtime called by that provider. No API-direct calls added.
- [x] **V. Protocols** -- new pipeline stages are injectable callables within the runtime module; `StorageProtocol` on the worker side is unchanged.
- [x] **VI. Test Layers** -- unit tests for all new runtime functions via `monkeypatch` on boto3; worker provider tests extended for `output_image_bytes` handling; 85% gate applies.
- [x] **VII. Observability** -- per-stage OTEL spans with `generation_id`, `stage_name`, `model_id`, `latency_ms`; `prompt_length` not prompt text; verification score/iteration emitted in telemetry.
- [x] **VIII. Security** -- SSRF check enforced by `policy.py` URL allowlist for `input_image_url`; no user-owned DB queries added; no secrets in code; all model IDs from env vars.

*Post-design re-check*: No new violations introduced by Phase 1 design artifacts.

## Project Structure

### Documentation (this feature)

```
specs/004-runtime-img-generation/
├── plan.md              <- this file
├── research.md          <- Phase 0 output
├── data-model.md        <- Phase 1 output
├── quickstart.md        <- Phase 1 output
├── contracts/           <- Phase 1 output
│   ├── runtime-response-contract.md
│   └── worker-agentcore-contract.md
└── tasks.md             <- Phase 2 (/speckit.tasks)
```

### Source Code (repository root)

```
runtimes/agentcore_img2img/app/
├── graph.py             <- REPLACE: implement full 3-stage pipeline + verification loop
├── contracts.py         <- EXTEND: add output_image_bytes to RuntimeInvocationResponse
├── settings.py          <- NEW: env-var config dataclass (read at invocation-time)
├── stages/
│   ├── __init__.py      <- NEW
│   ├── rewriter.py      <- NEW: Stage 1 - prompt rewriting + retry refinement
│   ├── generator.py     <- NEW: Stage 2 - SD + ControlNet invocation
│   └── verifier.py      <- NEW: Stage 3 - dual-axis composite verification
├── main.py              <- unchanged
└── policy.py            <- unchanged

runtimes/agentcore_img2img/tests/
├── test_graph.py        <- EXTEND: end-to-end pipeline tests
├── test_rewriter.py     <- NEW
├── test_generator.py    <- NEW
├── test_verifier.py     <- NEW
└── test_settings.py     <- NEW

worker/providers/
└── agentcore.py         <- EXTEND: handle output_image_bytes; upload to storage
```

## Phase 0: Research

*See [research.md](research.md)*

Key research questions resolved before Phase 1:
- R-001: Does AWS Bedrock offer a Stable Diffusion model with ControlNet depth/edge conditioning, and what is the exact Bedrock invocation format?
- R-002: Is Google Gemma available as a multimodal (image+text) model via Bedrock, and what is the multimodal message format?
- R-003: What is the AgentCore response body size limit?
- R-004: What structured JSON prompt format reliably elicits numeric sub-scores from the verification model?

## Phase 1: Design

*See [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)*

### Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Image bytes transport | Return base64 in response body (Option B) | Runtime has no storage credentials; worker already owns upload path |
| Verification model | Reuse Stage 1 model (PROMPT_REWRITE_MODEL_ID) | Avoids new dependency; one model for rewrite + verify |
| Score format | Structured JSON with two integer sub-scores (1-10) | Deterministic parsing; clamped as last resort |
| Score composition | 50/50 average normalised to 0-1 | Symmetric; no extra config parameter |
| Loop bounds | Iteration cap + wall-clock time budget | Both prevent cost/latency runaway |
| Prompt length control | System instruction constraint + SD_PROMPT_MAX_TOKENS truncation | Self-limiting first, hard truncation as backstop |
| Image dimension control | _resize_image preprocessing (already in codebase) | Zero new code |
| Output size control | JPEG re-encode to MAX_OUTPUT_IMAGE_BYTES ceiling | Prevents AgentCore response size violation |

## Staged Commits

Implementation is split into 6 atomic commits. Each commit leaves the codebase in a passing, deployable state.

> **Existing tests that must be modified** (not just new files added):
> - `runtimes/agentcore_img2img/tests/test_contracts.py` — Commit 1
> - `runtimes/agentcore_img2img/tests/test_graph.py` — Commit 4
> - `tests/worker/test_agentcore_provider.py` — Commit 5

---

### Commit 1 — `feat(runtime): add PipelineSettings and extend contracts`

**Files:**
- `runtimes/agentcore_img2img/app/settings.py` — NEW: `PipelineSettings.from_env()` dataclass
- `runtimes/agentcore_img2img/app/contracts.py` — add `output_image_bytes: str | None = None`; change `extra="forbid"` to `extra="ignore"` on response model
- `runtimes/agentcore_img2img/tests/test_settings.py` — NEW: unit tests for all env-var defaults and override behaviour
- `runtimes/agentcore_img2img/tests/test_contracts.py` — MODIFY:
  - Add test: `output_image_bytes` defaults to `None` when absent from response
  - Add test: valid base64 string is accepted in `output_image_bytes`
  - Add test: response with unknown extra fields no longer raises `ValidationError` (was `extra="forbid"`, now `extra="ignore"`)
  - Keep existing: `test_request_requires_mandatory_fields`, `test_request_rejects_empty_prompt`, `test_response_requires_remote_output_url`, `test_request_accepts_null_input_image_url` — all still valid, no changes needed

**Verification:** `pytest runtimes/agentcore_img2img/tests/test_contracts.py runtimes/agentcore_img2img/tests/test_settings.py -v`

**Why first:** Every subsequent stage depends on `PipelineSettings`; the contract extension is backward-compatible and unblocks the worker update in Commit 5.

---

### Commit 2 — `feat(runtime): Stage 1 — prompt rewriter`

**Files:**
- `runtimes/agentcore_img2img/app/stages/__init__.py` — NEW (empty)
- `runtimes/agentcore_img2img/app/stages/rewriter.py` — NEW: `rewrite_prompt()` using Nova Lite multimodal; handles empty output fallback; truncates to `SD_PROMPT_MAX_TOKENS`
- `runtimes/agentcore_img2img/tests/test_rewriter.py` — NEW: unit tests (mock Bedrock); empty output substitution; length truncation; Bedrock error propagation

**Verification:** `pytest runtimes/agentcore_img2img/tests/test_rewriter.py -v`

---

### Commit 3 — `feat(runtime): Stage 2 — SD ControlNet generator`

**Files:**
- `runtimes/agentcore_img2img/app/stages/generator.py` — NEW: `generate_image()` using `us.stability.stable-image-control-structure-v1:0`; `finish_reason` check; image preprocessing via `_resize_image`; output size enforcement to `MAX_OUTPUT_IMAGE_BYTES`
- `runtimes/agentcore_img2img/tests/test_generator.py` — NEW: unit tests; corrupt output handling; size ceiling enforcement; finish_reason failure path

**Verification:** `pytest runtimes/agentcore_img2img/tests/test_generator.py -v`

---

### Commit 4 — `feat(runtime): Stage 3 + verification loop — wire graph.py`

**Files:**
- `runtimes/agentcore_img2img/app/stages/verifier.py` — NEW: `verify_image()` with dual-image Nova Lite call; structured JSON parse + fallback; composite score calculation; correction context truncation
- `runtimes/agentcore_img2img/app/graph.py` — REPLACE: implement `run_graph()` orchestrating Stages 1–3 with `LoopState`; time budget pre-check; best-result tracking; OTEL spans per stage
- `runtimes/agentcore_img2img/tests/test_verifier.py` — NEW: unit tests; parse failure fail-open; out-of-range score clamping; composite score formula
- `runtimes/agentcore_img2img/tests/test_graph.py` — REPLACE (all existing tests removed, replaced with new suite):
  - *Remove*: `test_run_graph_without_image` — new graph requires `input_image_url`; no-image path is now an error
  - *Remove*: `test_run_graph_fetches_and_forwards_image_to_agent` — patches `_BEDROCK`/`_STRANDS_MODEL_ID` which no longer exist in `graph.py`
  - *Remove*: `test_run_graph_format_detected_from_url_extension` — same patch surface gone
  - *Remove*: `test_run_graph_image_fetch_failure_falls_back_gracefully` — new contract: fetch failure → hard error, not silent fallback
  - *Remove*: `test_run_graph_raises_without_output_base_url` — keep intent, rewrite to patch `PipelineSettings`
  - *Add*: end-to-end pipeline with mocked stages (threshold met on first iteration)
  - *Add*: loop exits after max iterations; returns best-scoring candidate
  - *Add*: loop exits on time budget pre-check; returns best candidate seen
  - *Add*: SD failure on all iterations → response has `output_image_bytes=None`, `generated_image_description` populated
  - *Add*: Stage 1 failure → raises, no partial result returned
  - *Add*: verification fail-open (parse failure) exits loop with current result
  - *Add*: missing `input_image_url` → `ValueError` before any model is called
  - *Add*: `RUNTIME_OUTPUT_BASE_URL` absent → `ValueError`

**Verification:** `pytest runtimes/agentcore_img2img/tests/ -v`

**Why together:** `verifier.py` and the loop in `graph.py` are tightly coupled; splitting them would leave `graph.py` in a broken state between commits.

---

### Commit 5 — `feat(worker): handle output_image_bytes from AgentCore runtime`

**Files:**
- `worker/providers/agentcore.py` — extend `AgentCoreResult` with `output_image_bytes`; remove `_enforce_metadata_only` method and its call site; add temp-file decode path in `_run_agent` return dict; wrap file I/O in `asyncio.to_thread`
- `tests/worker/test_agentcore_provider.py` — MODIFY:
  - *Remove*: `test_generate_rejects_binary_payload_fields` — this test asserts the guard being deleted; its intent is now inverted
  - *Add*: `test_generate_returns_output_image_bytes_when_present` — runtime response includes `output_image_bytes`; `AgentCoreResult.output_image_bytes` is populated
  - *Add*: `test_generate_output_image_bytes_absent_returns_none` — runtime response omits field; `AgentCoreResult.output_image_bytes` is `None`
  - *Add*: `test_generate_invalid_base64_in_output_image_bytes_raises` — corrupted base64 in response raises before returning
  - Keep existing: `test_generate_normalizes_response_and_enforces_metadata_only` — rename to `test_generate_normalizes_response`; remove the "enforces_metadata_only" assertion
  - Keep existing: `test_invoke_runtime_requires_runtime_arn`
  - Keep existing: `test_invoke_runtime_uses_supported_method_name`
  - Keep existing: `test_invoke_runtime_omits_runtime_session_id_when_none`

**Verification:** `pytest tests/worker/test_agentcore_provider.py -v`

**Why separate from runtime:** Worker and runtime are independently deployable. The worker update is backward-compatible (field is optional) so it can ship before or after the new runtime ZIP.

---

### Commit 6 — `chore(specs): finalise 004 planning artifacts`

**Files:**
- `specs/004-runtime-img-generation/` — all planning docs (already written; this commit locks them in alongside the implementation)
- `.github/copilot-instructions.md` — updated SPECKIT block pointing to 004 plan

**Verification:** `git diff --stat HEAD~1` — docs only, no source changes.

---

## Commit Order Rationale

```
Commit 1 (settings + contracts + test_contracts.py update)
    └── Commit 2 (rewriter — depends on PipelineSettings)
            └── Commit 3 (generator — depends on PipelineSettings)
                    └── Commit 4 (verifier + graph — depends on 2 + 3; test_graph.py replaced)
                            └── Commit 5 (worker — depends on contract from Commit 1; test_agentcore updated)
                                    └── Commit 6 (docs — no code deps)
```

Each commit is independently testable. Commits 2, 3, and 5 can be authored in parallel on separate worktrees if desired; they only converge at Commit 4.
