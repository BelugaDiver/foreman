# Tasks: Runtime Image Generation Pipeline

**Feature**: `004-runtime-img-generation` | **Date**: 2026-06-07
**Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)

---

## Phase 1 — Setup: Config + Contract Foundation

*Commit 1. All subsequent phases depend on `PipelineSettings`. Contract extension unblocks worker phase.*

- [X] T001 Create `PipelineSettings` dataclass with `from_env()` in `runtimes/agentcore_img2img/app/settings.py`
- [X] T002 Add `output_image_bytes: str | None = None` to `RuntimeInvocationResponse` and change `extra="forbid"` to `extra="ignore"` in `runtimes/agentcore_img2img/app/contracts.py`
- [X] T003 [P] Write unit tests for `PipelineSettings.from_env()` covering all env-var defaults, overrides, and startup warnings in `runtimes/agentcore_img2img/tests/test_settings.py`
- [X] T004 [P] Update `runtimes/agentcore_img2img/tests/test_contracts.py`: add tests for `output_image_bytes` default None, valid base64 accepted, and extra fields no longer raise `ValidationError`

---

## Phase 2 — Foundational: `stages/` Package Scaffold

*Must exist before Stages 1–3 are implemented.*

- [X] T005 Create `runtimes/agentcore_img2img/app/stages/__init__.py` (empty package marker)

---

## Phase 3 — User Story 1 + 2: Stage 1 — Prompt Rewriter

*Implements US1 (enriched prompt for generation) and US2 (prompt rewriting quality). Depends on T001, T005.*

- [X] T006 [US1] [US2] Implement `rewrite_prompt(original_prompt, image_b64, image_format, settings, correction_context) -> RewriteResult` in `runtimes/agentcore_img2img/app/stages/rewriter.py`:
  - Nova Lite `invoke_model` multimodal call (`schemaVersion: "messages-v1"`, base64 image in `source.bytes`)
  - System instruction with output length constraint and fallback directive
  - Empty/whitespace output → substitute `original_prompt`
  - Truncate enriched prompt to `settings.sd_prompt_max_tokens` before returning
  - When `correction_context` is provided, truncate to `settings.correction_context_max_tokens` and append to user message
  - Wrap boto3 call in `asyncio.to_thread()`
  - Return `RewriteResult(enriched_prompt, model_id, latency_ms)`
- [X] T007 [P] [US1] [US2] Write unit tests for `rewriter.py` in `runtimes/agentcore_img2img/tests/test_rewriter.py`:
  - Happy path: enriched prompt returned
  - Empty model output → original prompt substituted
  - Prompt truncated to `sd_prompt_max_tokens`
  - Correction context truncated to `correction_context_max_tokens` and included in call
  - Bedrock error propagates as exception (Stage 1 failure → no partial result)

---

## Phase 4 — User Story 1 + 3: Stage 2 — SD ControlNet Generator

*Implements US1 (actual image output) and US3 (graceful SD fallback). Depends on T001, T005.*

- [X] T008 [US1] [US3] Implement `generate_image(enriched_prompt, control_image_b64, settings) -> GenerationResult` in `runtimes/agentcore_img2img/app/stages/generator.py`:
  - Resize input image via `_resize_image` before base64 encoding (reuse from `graph.py`)
  - Invoke `settings.sd_model_id` (`us.stability.stable-image-control-structure-v1:0` default) with `{"prompt", "image", "control_strength", "negative_prompt", "seed", "output_format": "jpeg"}`
  - Check `finish_reasons[0]`: non-null → return `GenerationResult` with empty `image_bytes` and the finish reason
  - Decode `images[0]` from base64
  - If decoded size > `settings.max_output_image_bytes`: JPEG re-encode at reduced quality/dimensions until under ceiling; if still over → treat as SD failure
  - Wrap boto3 call in `asyncio.to_thread()`
  - Return `GenerationResult(image_bytes, image_b64, finish_reason, seed, model_id, latency_ms)`
- [X] T009 [P] [US1] [US3] [US4] Write unit tests for `generator.py` in `runtimes/agentcore_img2img/tests/test_generator.py`:
  - Happy path: image bytes returned, `finish_reason` is None
  - `finish_reason` non-null → `GenerationResult` with empty bytes (SD failure)
  - Output image over `max_output_image_bytes` → compressed to fit
  - Output still over limit after compression → empty bytes (treated as SD failure)
  - Bedrock error propagates as exception
  - `SD_MODEL_ID` env var override is passed as `modelId` in the Bedrock invoke call (FR-010, SC-005)

---

## Phase 5 — User Story 5: Stage 3 + Verification Loop — Wire `graph.py`

*The agent harness. Implements US5 (verification loop), completes US1 and US3. Depends on T006, T008.*

- [X] T010 [US5] Implement `verify_image(original_prompt, reference_image_b64, candidate_image_b64, settings, correction_context_max_tokens) -> VerificationResult` in `runtimes/agentcore_img2img/app/stages/verifier.py`:
  - Nova Lite `invoke_model` call with two images (reference + candidate) and original prompt
  - System instruction: respond only with JSON, no prose
  - User message: inline schema `{"prompt_alignment": <1-10>, "structural_fidelity": <1-10>, "description": "<sentence>"}`
  - Parse response: direct JSON parse → regex extract → fail-open (scores = 10/10, `parse_failed=True`)
  - Clamp sub-scores to `[1, 10]`; normalise to `[0, 1]`; composite = 50/50 average
  - Return `VerificationResult(prompt_alignment, structural_fidelity, composite_score, description, model_id, latency_ms, parse_failed)`
- [X] T011 [US5] Replace `run_graph()` in `runtimes/agentcore_img2img/app/graph.py` with full 3-stage pipeline + `LoopState` verification loop:
  - Reject missing `input_image_url` before any model call
  - Fetch + validate input image (PIL decode; reject invalid format with actionable error)
  - Resize image via `_resize_image`
  - Call `rewrite_prompt()` (Stage 1); propagate Stage 1 errors without partial result
  - Enter verification loop:
    - Pre-iteration time budget check: if `remaining < settings.verification_iter_estimate_seconds` → exit (`time_budget_precheck`)
    - Call `generate_image()` (Stage 2); on SD failure update loop state, continue to next iteration or exit
    - Call `verify_image()` (Stage 3); on parse failure → fail-open, exit loop
    - Update `LoopState.best_*` if `current_score > best_score`
    - Exit if `composite_score >= settings.verification_alignment_threshold` (`threshold_met`)
    - Exit if `iteration == settings.verification_max_iterations` (`max_iterations`)
    - Else: set `correction_context = verification.description`, increment, loop
  - On loop exit: base64-encode best image, enforce `max_output_image_bytes` ceiling
  - Return dict matching `RuntimeInvocationResponse` fields
  - OTEL spans: one per stage with `generation_id`, `model_id`, `latency_ms`; verification iterations logged with `composite_score`, `exit_reason`
- [X] T012 [P] [US5] Write unit tests for `verifier.py` in `runtimes/agentcore_img2img/tests/test_verifier.py`:
  - Happy path: both sub-scores parsed, composite calculated correctly
  - Score outside 1–10 → clamped before normalisation
  - One sub-score absent → substituted with present score
  - JSON parse fails entirely → fail-open (composite = 1.0, `parse_failed=True`)
  - Bedrock error → propagates (caller handles fail-open)
- [X] T013 [US1] [US3] [US5] Replace `runtimes/agentcore_img2img/tests/test_graph.py` with new suite (all 5 existing tests removed; new tests added):
  - End-to-end: threshold met on first iteration → `output_image_bytes` present, `generated_image_description` set
  - Loop exits after `max_iterations` → best-scoring candidate returned, not an error
  - Loop exits on time budget pre-check → best candidate returned; `exit_reason = "time_budget_precheck"`
  - SD failure on all iterations → `output_image_bytes=None`, `generated_image_description` from Stage 1 enriched prompt (FR-007, FR-020)
  - No SD generation ever succeeded (all fail before any result) → description-only response, no exception (FR-020)
  - Stage 1 failure → exception raised, no partial result
  - Verification fail-open (parse failure) → exits loop, returns current result
  - Missing `input_image_url` → `ValueError` before any model is called
  - Missing `RUNTIME_OUTPUT_BASE_URL` → `ValueError`
  - OTEL spans emitted with `generation_id`, `model_id`, `latency_ms` attributes for Stage 1, Stage 2, and Stage 3 (FR-012, SC-006)
  - Exit reason logged in structured telemetry for each of the 5 exit conditions (FR-022, SC-011)

---

## Phase 6 — User Story 1: Worker `AgentCoreProvider` Update

*Implements US1 acceptance scenario 2 (worker uploads bytes). Can be developed in parallel with Phases 3–5. Depends on T002.*

- [X] T014 [US1] Extend `AgentCoreResult` with `output_image_bytes: str | None = None` in `worker/providers/agentcore.py`
- [X] T015 [US1] Remove `_enforce_metadata_only()` method and its call site from `worker/providers/agentcore.py`
- [X] T016 [US1] Update `AgentCoreProvider.generate()` in `worker/providers/agentcore.py` to parse `output_image_bytes` from the runtime response and populate `AgentCoreResult.output_image_bytes`
- [X] T017 [US1] Update `_run_agent()` return-dict construction in `worker/providers/agentcore.py`: if `output_image_bytes` is present and non-empty, decode base64 → write to temp file → return `{"output_image_path": tmp.name, ...}`; otherwise keep existing `output_image_url` path; wrap file I/O in `asyncio.to_thread()`
- [X] T018 [P] [US1] Update `tests/worker/test_agentcore_provider.py`:
  - Remove: `test_generate_rejects_binary_payload_fields`
  - Rename: `test_generate_normalizes_response_and_enforces_metadata_only` → `test_generate_normalizes_response`; remove the metadata-only assertion
  - Add: `test_generate_returns_output_image_bytes_when_present` — response with `output_image_bytes` → field populated on `AgentCoreResult`
  - Add: `test_generate_output_image_bytes_absent_returns_none` — field absent → `AgentCoreResult.output_image_bytes` is None
  - Add: `test_generate_invalid_base64_raises` — corrupted base64 → raises before returning
  - Keep: `test_invoke_runtime_requires_runtime_arn`, `test_invoke_runtime_uses_supported_method_name`, `test_invoke_runtime_omits_runtime_session_id_when_none`

---

## Phase 7 — Polish: Integration Smoke Test + Coverage Gate

- [X] T019 [P] Run full test suite and confirm ≥85% coverage on all modified modules: `pytest runtimes/agentcore_img2img/tests/ tests/worker/test_agentcore_provider.py --cov=runtimes/agentcore_img2img/app --cov=worker/providers/agentcore --cov-report=term-missing`
- [X] T020 Commit all planning docs and updated `.github/copilot-instructions.md` as final `chore(specs)` commit

---

## Dependencies

```
T001 (PipelineSettings)
    └── T006 (rewriter — imports PipelineSettings)
    └── T008 (generator — imports PipelineSettings)
    └── T011 (graph — imports PipelineSettings)

T002 (contracts extension)
    └── T014–T017 (worker — reads output_image_bytes from response)

T005 (stages/__init__.py)
    └── T006, T008, T010

T006 (rewriter) ──────────────┐
T008 (generator) ─────────────┤── T010, T011 (verifier + graph)
T010 (verifier) ──────────────┘

T011 (graph) ─────────────────── T013 (test_graph.py — tests the new graph)

T014–T017 (agentcore.py) ────── T018 (test_agentcore_provider.py)

T011, T017 ──────────────────── T019 (coverage gate)
T019 ────────────────────────── T020 (final commit)
```

## Parallel Execution Opportunities

- **T003 + T004** (test_settings + test_contracts update) — parallel with each other after T001/T002
- **T006 + T007** (rewriter impl + tests) — parallel with **T008 + T009** (generator impl + tests)
- **T014–T017** (worker provider update) — fully parallel with Phases 3–5 (runtime stages)
- **T012** (test_verifier) — parallel with T013 (test_graph) once T010/T011 exist

## Implementation Strategy

**MVP scope (US1 end-to-end)**: T001 → T002 → T005 → T008 → T011 (single-pass, no rewrite or verify) → T014–T017 → T019. This delivers a working image-generation pipeline. Add T006/T010 to enable the full agent harness.

**Recommended order per the staged-commit plan in plan.md:**

```
Commit 1: T001 → T002 → T003 → T004
Commit 2: T005 → T006 → T007
Commit 3: T008 → T009
Commit 4: T010 → T011 → T012 → T013
Commit 5: T014 → T015 → T016 → T017 → T018
Commit 6: T019 → T020
```
