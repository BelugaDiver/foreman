# Feature Specification: Runtime Image Generation Pipeline

**Feature Branch**: `004-runtime-img-generation`
**Created**: 2026-06-07
**Status**: Draft
**Input**: User description: "Extend the agentcore_img2img runtime into a fully-featured agent harness: (1) prompt rewriting via a cheap multimodal model, (2) Stable Diffusion + ControlNet image generation using the rewritten prompt and input image, (3) return output image bytes to the worker for storage."

## Clarifications

### Session 2026-06-07

- Q: Should the runtime store the generated image directly to S3, or return image bytes to the caller? → A: Option B (preferred). Runtime returns base64-encoded image bytes in the response payload. The worker — which already has S3/storage access — handles upload and populates `output_image_url`. This decouples storage from the runtime and removes location/region dependency.
- Q: Which model should perform prompt rewriting? → A: A cheap multimodal model (e.g., Google Gemma or equivalent available via Amazon Bedrock) that can accept both text and the input image. Specific model ID is configurable via environment variable.
- Q: What ControlNet mode should be used for Stable Diffusion? → A: Depth or edge control (operator-configurable via environment variable). The input image serves as the control image. SD model ID is also configurable via environment variable.
- Q: What should happen if the SD generation step fails? → A: Graceful fallback — runtime returns only the description from the prompt-rewriting step with no image bytes. Worker handles the absence of `output_image_bytes` by writing a null/empty `output_image_url`.
- Q: Does this change the existing worker queue contract? → A: No. The `RuntimeInvocationRequest` schema is unchanged. The `RuntimeInvocationResponse` gains one new optional field (`output_image_bytes`). Existing workers that ignore unknown fields are unaffected; updated workers check for the field and upload when present.

### Session 2026-06-07 (Verification Loop)

- Q: How does the runtime verify that the generated image matches the original prompt? → A: The same multimodal model used for Stage 1 (prompt rewriting) is reused to describe the generated output image; the runtime checks semantic alignment between that description and the user's original prompt. This avoids a new model dependency and produces human-readable acceptance/rejection reasoning.
- Q: How is alignment scored to decide whether to exit the loop? → A: The verification model is prompted to return a structured score (1–10) embedded in its response alongside its description; the runtime parses and normalises this to 0–1 for comparison against `VERIFICATION_ALIGNMENT_THRESHOLD`.
- Q: How is the verification loop bounded for cost and speed? → A: The loop is bounded by both a maximum iteration count (`VERIFICATION_MAX_ITERATIONS`) AND a wall-clock time budget (`VERIFICATION_TIME_BUDGET_SECONDS`). Whichever limit is hit first terminates the loop. On budget exhaustion the runtime returns the best-scoring result seen so far (same as max-iteration behaviour).
- Q: What information is fed back into the next prompt on a failed verification iteration? → A: The alignment description produced by the verification step is passed as "correction context" back to the Stage 1 prompt-rewriting model, alongside the original prompt. The model produces a revised enriched prompt that incorporates the specific misalignment feedback before the next SD generation attempt.
- Q: Should verification assess only prompt alignment, or also structural fidelity to the input image? → A: Both. The verification model receives the candidate output image, the original input image, and the original prompt in a single call; it returns a composite score covering (1) prompt text alignment and (2) structural/spatial fidelity to the input image composition.
- Q: How should the two sub-scores be combined into the single composite score? → A: Equal 50/50 average of the prompt alignment sub-score and the structural fidelity sub-score. Both are normalised to 0–1 before averaging; the result is compared against `VERIFICATION_ALIGNMENT_THRESHOLD`.

### Session 2026-06-07 (Edge Case Mitigations)

- Q: How should oversized enriched prompts be handled to prevent SD model breakage? → A: The Stage 1 system instruction includes an explicit output length constraint so the model self-limits; `SD_PROMPT_MAX_TOKENS` provides a server-side truncation backstop before the prompt is passed to SD.
- Q: How should an empty enriched prompt from Stage 1 be handled? → A: The Stage 1 system instruction includes a fallback directive ("return the original prompt unchanged if no description can be produced"); runtime additionally substitutes the original prompt if the output is still blank. No breakage.
- Q: How should oversized correction context be handled on retry? → A: Correction context is truncated to `CORRECTION_CONTEXT_MAX_TOKENS` before being appended to the rewrite prompt for the next iteration.
- Q: How should input images with unsupported dimensions be handled? → A: Runtime pre-processes the image through the existing `_resize_image` utility before passing it to any model; no hard failure.
- Q: How should out-of-range verification scores be handled without breaking the loop? → A: Verification model is prompted with a structured JSON response format to enforce the 1–10 schema; runtime clamps any out-of-range value as a last resort. No breakage.
- Q: How should an output image that exceeds the AgentCore response size limit be handled? → A: Runtime compresses and/or resizes the generated image (JPEG re-encode at reduced quality/dimensions) to stay under `MAX_OUTPUT_IMAGE_BYTES` before base64 encoding; only falls back to description-only response if the image cannot be brought under the limit after compression.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — End-to-End Image Generation (Priority: P1)

As a platform user, when I submit an img2img generation request, the runtime produces an actual output image derived from my input image and my prompt — not just a text description.

**Why this priority**: The entire purpose of this feature is to produce a real output image. Without P1, no other story delivers user value.

**Independent Test**: Submit a valid `RuntimeInvocationRequest` with a prompt and input image URL, verify the response contains `output_image_bytes` (non-empty base64 string) and a non-empty `generated_image_description`.

**Acceptance Scenarios**:

1. **Given** a valid request with a prompt and accessible input image URL, **When** the runtime processes it, **Then** the response includes `output_image_bytes` (base64-encoded) representing the generated image, `generated_image_description` from the prompt-rewriting step, and `model_used` identifying the SD model.
2. **Given** a valid request is processed successfully, **When** the worker receives the response, **Then** the worker uploads `output_image_bytes` to storage and writes the resulting URL to `output_image_url` on the generation record.
3. **Given** the input image URL is inaccessible or invalid, **When** the runtime attempts to fetch it, **Then** the runtime rejects the request with an actionable error before invoking any model.

---

### User Story 2 — Prompt Rewriting Enriches Generation Quality (Priority: P2)

As a platform user, my original prompt is automatically enriched with visual context from the input image before image generation, so the output better reflects both the image content and my intent.

**Why this priority**: Prompt rewriting is the key quality improvement over a direct passthrough. Without it, generation results are less coherent with the input image.

**Independent Test**: Submit a short prompt; verify the `generated_image_description` in the response is longer/richer than the original prompt and references observable features of the input image.

**Acceptance Scenarios**:

1. **Given** a terse user prompt and an input image, **When** the prompt-rewriting step runs, **Then** the enriched prompt passed to the SD model incorporates descriptive detail derived from the image content.
2. **Given** the prompt-rewriting model is unavailable or returns an error, **When** the runtime handles this failure, **Then** execution halts and the caller receives a clear error — the SD step is not invoked with an unverified prompt.
3. **Given** the operator has configured a specific prompt-rewriting model via environment variable, **When** the runtime runs, **Then** that model is used for the rewriting step.

---

### User Story 3 — Graceful Degradation on SD Failure (Priority: P2)

As a platform operator, when the Stable Diffusion generation step fails, the runtime returns a partial result (description only, no image) so the worker can handle the failure gracefully rather than crashing.

**Why this priority**: Resilience during SD failures is critical for pipeline reliability; the prompt-rewriting output still has value for diagnostics.

**Independent Test**: Configure the SD model to return an error; verify the response omits `output_image_bytes` but still contains `generated_image_description`, and that the worker writes a null/empty `output_image_url` without raising an unhandled exception.

**Acceptance Scenarios**:

1. **Given** the SD model invocation fails (timeout, model error, quota exceeded), **When** the runtime handles the failure, **Then** the response contains `generated_image_description` from the rewriting step, omits `output_image_bytes`, and includes a machine-readable failure indicator.
2. **Given** the runtime returns a response without `output_image_bytes`, **When** the worker processes it, **Then** the worker writes a null or empty `output_image_url` and does not attempt a storage upload.

---

### User Story 5 — Verification Loop Ensures Prompt Fidelity (Priority: P2)

As a platform user, after each SD generation attempt the runtime checks whether the output image faithfully reflects my original prompt, and retries generation with a refined prompt if not — so I receive the best available result rather than a first-attempt output.

**Why this priority**: Without verification, a misaligned first generation is silently accepted. The loop is the defining "agent harness" behaviour that distinguishes this from a single-pass pipeline.

**Independent Test**: Submit a request where the first generation is expected to misalign (e.g., a style-heavy prompt with a plain input image); confirm the runtime performs at least one retry and that the final `generated_image_description` reflects the verification outcome and iteration count.

**Acceptance Scenarios**:

1. **Given** the first generated image is assessed as misaligned with the original prompt, **When** the verification step runs, **Then** the runtime refines the enriched prompt using the misalignment feedback and re-invokes SD generation.
2. **Given** the generated image is assessed as sufficiently aligned with the original prompt, **When** the verification step runs, **Then** the runtime exits the loop and returns the accepted image.
3. **Given** the maximum iteration count is reached without an accepted result, **When** the loop terminates, **Then** the runtime returns the best-scoring generation found so far (not a failure response), and includes the iteration count and final alignment score in telemetry.
4. **Given** the verification model call fails on any iteration, **When** the runtime handles this, **Then** it treats the current result as accepted (fail-open) and exits the loop to avoid infinite retry.

---

### User Story 4 — Configurable Models and ControlNet Mode (Priority: P3)

As a platform operator, I can configure the prompt-rewriting model, the SD model, and the ControlNet mode via environment variables so the runtime can be tuned or updated without code changes.

**Why this priority**: Operational flexibility is important but does not block core functionality if hardcoded defaults are used initially.

**Independent Test**: Set each environment variable to a non-default valid value, invoke the runtime, and confirm the correct model IDs and ControlNet mode are reflected in telemetry or `model_used`.

**Acceptance Scenarios**:

1. **Given** `PROMPT_REWRITE_MODEL_ID` is set, **When** the runtime starts, **Then** that model ID is used for all prompt-rewriting invocations during that session.
2. **Given** `SD_MODEL_ID` is set, **When** the runtime starts, **Then** that model ID is used for all SD generation invocations during that session.
3. **Given** `CONTROLNET_MODE` is set to a supported value (e.g., `depth` or `edge`), **When** image generation runs, **Then** the specified ControlNet conditioning mode is applied to the input image.
4. **Given** a required environment variable is absent at startup, **When** the runtime initializes, **Then** it uses a documented default value and emits a startup warning.

---

### Edge Cases

**Input / preprocessing**

- Input image URL is accessible but content is not a valid image format — runtime attempts PIL decode; on failure, rejects before invoking any model with an actionable error.
- Input image dimensions fall outside the SD model's supported range — runtime resizes the image to fit within the model's max side length before passing it (same `_resize_image` pattern already present in the codebase); no breakage.
- Runtime is invoked without `input_image_url` — rejected immediately with an actionable error before invoking any model.

**Prompt size and content**

- Enriched prompt exceeds the SD model's token limit — the Stage 1 prompt-rewriting system instruction includes an explicit output length constraint (e.g., "respond in no more than N tokens") so the model self-limits; runtime also truncates server-side to the configured `SD_PROMPT_MAX_TOKENS` before invoking SD.
- Prompt-rewriting model returns an empty or whitespace-only enriched prompt — the Stage 1 system instruction includes a fallback directive: "if you cannot produce a description, return the original prompt unchanged"; runtime additionally checks for emptiness and substitutes the original prompt if the output is still blank; no breakage.
- Correction context from a failed verification iteration is too long to include in the next prompt — runtime truncates correction context to `CORRECTION_CONTEXT_MAX_TOKENS` before appending to the rewrite prompt.

**Verification scoring**

- Verification model returns a score outside the 1–10 range — the verification system instruction uses a structured JSON response format to enforce schema; runtime clamps any out-of-range value to [1, 10] as a last resort; no breakage.
- Verification model is prompted with both images but returns only one sub-score — structured JSON response format prevents this; if one sub-score is genuinely absent, runtime substitutes the present score for both (conservative, avoids penalising a partial response unfairly).
- Verification model returns a response that cannot be parsed — runtime treats the current result as accepted (fail-open) and exits the loop; logged in telemetry.
- All iterations produce identical alignment scores (no improvement signal) — loop terminates at max iteration cap; best-scoring (or only) result is returned.

**Timing and budget**

- Time budget expires partway through an in-flight SD generation call — runtime completes the in-progress call, evaluates the result, and then exits the loop (does not abandon mid-call).
- `VERIFICATION_TIME_BUDGET_SECONDS` is set so low that zero iterations can complete — runtime skips the loop entirely and returns the Stage 1 description with no image bytes; logged as a configuration warning.

**Output size**

- SD model returns image bytes that fail integrity validation (corrupt, zero-length) — runtime discards the result and records a SD-stage failure; falls back to description-only response.
- `output_image_bytes` payload exceeds the AgentCore response size limit — runtime compresses and/or resizes the output image (JPEG re-encode at reduced quality/dimensions) before base64 encoding, targeting a configurable `MAX_OUTPUT_IMAGE_BYTES` ceiling; if still over limit after compression, runtime falls back to description-only response.

**Worker-side**

- Worker receives a response with `output_image_bytes` but the storage upload fails — handled by the worker's existing retry/error path; generation record is marked with an error status; no runtime-side impact.
- Both prompt-rewriting and SD steps fail simultaneously — treated as a Stage 1 failure (runtime returns an error response, no partial result); this is already the most conservative path and requires no special-casing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Runtime MUST implement a three-stage pipeline with a verification loop: (1) prompt rewriting via a multimodal model, (2) image generation via Stable Diffusion with ControlNet conditioning, and (3) a verification loop that scores each candidate image against the original prompt and input image, retrying with a refined prompt until the score meets a threshold, the iteration cap is reached, or the time budget is exhausted.
- **FR-002**: Prompt-rewriting stage MUST accept both the user's original prompt text and the input image (fetched from `input_image_url`) as inputs to the multimodal model.
- **FR-003**: Image-generation stage MUST pass the enriched prompt from FR-002 and the input image as a ControlNet control image to the SD model.
- **FR-004**: Runtime MUST return `output_image_bytes` as a base64-encoded string in `RuntimeInvocationResponse` when image generation succeeds.
- **FR-005**: Runtime MUST NOT attempt to upload images to any storage service directly; storage responsibility MUST remain with the worker.
- **FR-006**: Worker MUST be updated to detect the presence of `output_image_bytes` in the runtime response and, when present, upload the bytes to the configured storage backend before writing `output_image_url` to the generation record.
- **FR-007**: Runtime MUST fall back gracefully when SD generation fails: return a response containing `generated_image_description` and no `output_image_bytes`. `generated_image_description` MUST be populated from the last successful `VerificationResult.description` if one exists from a prior iteration; otherwise it falls back to the Stage 1 enriched prompt.
- **FR-008**: `input_image_url` MUST be treated as a required field for this runtime variant; the runtime MUST reject requests that omit it with an actionable error before invoking any model.
- **FR-009**: Prompt-rewriting model ID MUST be configurable via the `PROMPT_REWRITE_MODEL_ID` environment variable, with a documented default.
- **FR-010**: SD model ID MUST be configurable via the `SD_MODEL_ID` environment variable, with a documented default.
- **FR-011**: ControlNet conditioning mode MUST be configurable via the `CONTROLNET_MODE` environment variable; supported values are `depth` and `edge`, with a documented default.
- **FR-012**: Runtime MUST emit structured telemetry for each pipeline stage (prompt rewriting and image generation), including stage name, model ID used, latency, and success/failure outcome.
- **FR-013**: Runtime MUST remain compatible with the existing `RuntimeInvocationRequest` schema — no new required request fields are added.
- **FR-014**: `RuntimeInvocationResponse` MUST be extended with one new optional field: `output_image_bytes` (nullable base64 string). All existing fields (`output_image_url`, `generated_image_description`, `model_used`) remain unchanged.
- **FR-015**: Worker MUST handle `output_image_bytes` being absent (null or missing) without raising an unhandled exception.
- **FR-016**: After each SD generation attempt, the runtime MUST invoke the Stage 1 multimodal model in a single verification call that receives: (a) the candidate output image, (b) the original input image, and (c) the original user prompt. The model MUST return two structured sub-scores (1–10 each): prompt text alignment and structural/spatial fidelity to the input image composition, plus a human-readable alignment description. The runtime normalises each sub-score to 0–1 and averages them equally to form the composite score compared against `VERIFICATION_ALIGNMENT_THRESHOLD`.
- **FR-017**: When a loop iteration produces a score below the threshold, the runtime MUST pass the verification model's alignment description as correction context to the Stage 1 prompt-rewriting model; the model produces a revised enriched prompt before the next SD generation attempt.
- **FR-018**: Maximum iteration count MUST be configurable via the `VERIFICATION_MAX_ITERATIONS` environment variable, with a documented default (e.g., 3).
- **FR-019**: Alignment threshold MUST be configurable via the `VERIFICATION_ALIGNMENT_THRESHOLD` environment variable, with a documented default (e.g., 0.75).
- **FR-020**: When the loop terminates due to reaching max iterations, the runtime MUST return the best-scoring image seen across all iterations (not an error response). If no SD generation ever succeeded, the runtime MUST return a description-only response (same as the SD failure fallback).
- **FR-021**: If the verification model call fails on any iteration, the runtime MUST treat the current result as accepted (fail-open) and exit the loop.
- **FR-022**: Per-iteration alignment score, iteration count, and final acceptance reason MUST be included in structured telemetry.
- **FR-024**: A wall-clock time budget for the entire verification loop MUST be configurable via `VERIFICATION_TIME_BUDGET_SECONDS`, with a documented default. The loop MUST exit and return the best result seen when this budget is exhausted, regardless of iteration count.
- **FR-025**: At the start of each loop iteration, the runtime MUST check whether the remaining time budget is sufficient to complete one more SD + verification round-trip (using a configurable per-iteration time estimate); if not, it MUST exit early rather than begin an iteration that cannot complete within budget.

### Key Entities

- **Enriched Prompt**: The output of the prompt-rewriting stage — a richer text description combining the user's original prompt and image-derived context, used as the SD generation prompt.
- **Correction Context**: The alignment description returned by the verification model on a failed iteration; passed back to the Stage 1 prompt-rewriting model to produce a revised enriched prompt for the next retry.
- **Control Image**: The input image fetched from `input_image_url`, used as the ControlNet conditioning signal for the SD model.
- **Composite Verification Score**: The equal 50/50 average of the prompt alignment sub-score and the structural fidelity sub-score, each normalised to 0–1 from the model's 1–10 output; compared against `VERIFICATION_ALIGNMENT_THRESHOLD` to decide loop exit.
- **Output Image Bytes**: The raw bytes of the SD-generated image, base64-encoded and returned to the worker in `output_image_bytes`.
- **Pipeline Stage Result**: Per-stage telemetry record capturing model ID, latency, and outcome for each of the two pipeline steps.

## Architecture / Design Notes

### Two-Stage Pipeline

```
RuntimeInvocationRequest
        │
        ▼
[Stage 1: Prompt Rewriting]
  • Model: multimodal LLM (Nova Lite / equivalent), configured via PROMPT_REWRITE_MODEL_ID
  • Inputs: original prompt text + input image bytes (fetched from input_image_url)
  • Output: enriched_prompt (string)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│              Verification Loop (max N iterations)        │
│                                                         │
│  [Stage 2: SD + ControlNet Image Generation]            │
│    • Model: Stable Diffusion, via SD_MODEL_ID           │
│    • ControlNet mode: CONTROLNET_MODE (depth | edge)    │
│    • Inputs: enriched_prompt + input image (control)    │
│    • Output: candidate image bytes                      │
│                          │                              │
│  [Stage 3: Verification] │                              │
│    • Model: same as Stage 1 (PROMPT_REWRITE_MODEL_ID)   │
│    • Inputs: candidate image + input image + prompt     │
│    • Output: composite score (prompt + structural) +    │
│              human-readable alignment description       │
│                          │                              │
│    aligned? ─────────────┤ YES → exit loop              │
│                          │ NO  → refine enriched_prompt │
│                          │       with misalignment      │
│                          │       feedback, retry        │
└─────────────────────────────────────────────────────────┘
        │
  (best-scoring result selected on max-iteration exit)
        │
        ▼
RuntimeInvocationResponse
  • output_image_bytes: base64(accepted image bytes)  ← new, optional
  • generated_image_description: final alignment desc  ← existing
  • model_used: SD_MODEL_ID                            ← existing
  • output_image_url: null (worker fills this in)      ← existing, not set by runtime
```

### Image Storage — Option B (Preferred)

The runtime does **not** write to any storage service. It returns the generated image as `output_image_bytes` (base64) in the response body. The worker, which already holds S3/storage credentials and access patterns, performs the upload and derives the final `output_image_url`.

**Why Option B over Option A (runtime calls Foreman images API):**

| Concern | Option A (runtime → Foreman API) | Option B (bytes in response, worker uploads) |
|---------|----------------------------------|----------------------------------------------|
| Deployment isolation | Runtime must reach Foreman API — breaks in isolated/offline deployments | No outbound dependency from runtime |
| Credential scope | Runtime needs Foreman API credentials in addition to Bedrock access | Runtime needs only Bedrock access |
| Failure modes | Storage failure is unrecoverable from runtime; worker has no retry surface | Worker controls upload retry with its existing logic |
| Contract coupling | Runtime must know Foreman's upload URL contract | Runtime contract is self-contained |
| Response size | Image bytes not in response; only URL returned | Image bytes in response body — must stay within AgentCore response size limit |

Option B's only risk (response size) is mitigated by validating generated image size before encoding and failing gracefully if it exceeds the limit.

### Contract Changes

**`RuntimeInvocationResponse` (contracts.py)**
- Add: `output_image_bytes: Optional[str] = None` — base64-encoded generated image. Null when generation failed or was skipped.
- Existing fields unchanged: `output_image_url`, `generated_image_description`, `model_used`.

**Worker (existing, must be updated)**
- After receiving `RuntimeInvocationResponse`, check `output_image_bytes`.
- If present and non-null: upload bytes to storage, obtain URL, write to generation record's `output_image_url`.
- If absent or null: write null/empty `output_image_url` (existing behavior preserved).

**`RuntimeInvocationRequest` (contracts.py)**
- No changes. `input_image_url` was already defined; it is now treated as required by the pipeline logic (enforced at runtime, not schema level, to avoid breaking the existing contract).

### Model Configuration

| Environment Variable | Purpose | Example Default |
|---------------------|---------|-----------------|
| `PROMPT_REWRITE_MODEL_ID` | Multimodal model for Stage 1 prompt enrichment and Stage 3 verification | `amazon.nova-lite-v1:0` |
| `SD_MODEL_ID` | Stability AI Control Structure model for Stage 2 generation | `us.stability.stable-image-control-structure-v1:0` |
| `CONTROLNET_MODE` | ControlNet conditioning type — maps to Bedrock model: `depth` = control-structure, `edge` = control-sketch | `depth` |
| `VERIFICATION_MAX_ITERATIONS` | Maximum SD generation + verification loop iterations | `3` |
| `VERIFICATION_ALIGNMENT_THRESHOLD` | Minimum composite alignment score (0–1) to accept a generated image | `0.75` |
| `VERIFICATION_TIME_BUDGET_SECONDS` | Wall-clock time budget for the entire verification loop | `60` |
| `VERIFICATION_ITER_ESTIMATE_SECONDS` | Estimated time per SD + verification round-trip; used for pre-iteration budget check | `18` |
| `SD_PROMPT_MAX_TOKENS` | Maximum token length for the enriched prompt passed to the SD model; prompt is truncated server-side if exceeded | `300` |
| `CORRECTION_CONTEXT_MAX_TOKENS` | Maximum token length of the correction context appended to rewrite prompts on retry | `150` |
| `MAX_OUTPUT_IMAGE_BYTES` | Maximum byte size of the output image before base64 encoding; runtime compresses/resizes to stay under this ceiling | `1048576` (1 MB) |

All three variables have documented defaults; absent variables emit a startup warning and use the default.

### Fallback Behavior

If Stage 2 (SD generation) fails for any reason (model error, timeout, size validation failure):
1. Runtime logs the failure with structured telemetry.
2. Runtime returns `RuntimeInvocationResponse` with `generated_image_description` populated from Stage 1 and `output_image_bytes` set to null.
3. Worker detects null `output_image_bytes`, skips storage upload, writes null `output_image_url`.
4. Generation record is marked with an appropriate status (handled by worker's existing error path).

If Stage 1 (prompt rewriting) fails:
1. Runtime logs the failure and does **not** proceed to Stage 2.
2. Runtime returns an error response to the worker (no partial result).

**Verification loop exit conditions (in priority order)**:
1. Alignment score meets or exceeds `VERIFICATION_ALIGNMENT_THRESHOLD` → return current result.
2. Verification model call fails → treat current result as accepted (fail-open), return current result.
3. Remaining time budget < `VERIFICATION_ITER_ESTIMATE_SECONDS` → exit early, return best-scoring result seen.
4. Wall-clock elapsed time exceeds `VERIFICATION_TIME_BUDGET_SECONDS` → return best-scoring result seen.
5. Iteration count reaches `VERIFICATION_MAX_ITERATIONS` → return best-scoring result seen across all iterations.

All time-budget or iteration-cap exits MUST be recorded in telemetry with the exit reason.

## Out of Scope

- Changes to Foreman API endpoints (`/projects/{project_id}/images` or any other API route).
- Changes to the worker queue message schema or SQS message attribute contract.
- Authentication or authorization changes to any Foreman service.
- Multi-image generation (batch output) — this feature produces exactly one output image per invocation.
- Video or animated output formats.
- User-facing UI changes for configuring ControlNet mode or model selection.
- Runtime deployment infrastructure (Terraform, IAM roles, container registry) — covered by spec 003.
- Style-ID-to-ControlNet-parameter mapping logic — treated as a future enhancement.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid img2img invocations with accessible input images and operational models return `output_image_bytes` in the response.
- **SC-002**: Workers successfully upload the returned image bytes and write a valid `output_image_url` for at least 99% of invocations where `output_image_bytes` is present.
- **SC-003**: Prompt-rewriting stage produces an enriched prompt longer than the original for at least 90% of non-trivial input prompts in integration testing.
- **SC-004**: SD generation failures result in a graceful partial response (description only) with zero unhandled exceptions in the runtime process.
- **SC-005**: All three model/mode configuration variables take effect within one runtime restart, verified by telemetry reflecting the configured values.
- **SC-006**: Pipeline stage telemetry is emitted for 100% of invocations, capturing model ID, latency, and success/failure for each stage.
- **SC-007**: Response `output_image_bytes` payload remains within the AgentCore response size limit for all standard generation outputs.
- **SC-008**: At least one verification retry improves the composite alignment score in ≥50% of multi-iteration test runs.
- **SC-009**: Max-iteration exits always return a valid image (never an error response) when at least one SD generation attempt succeeded.
- **SC-010**: The verification loop NEVER exceeds `VERIFICATION_TIME_BUDGET_SECONDS` + one iteration's wall-clock time (i.e., it does not abandon in-flight model calls).
- **SC-011**: Telemetry records the loop exit reason (score threshold met / time budget / iteration cap / verification failure) for 100% of invocations.
- **SC-012**: Structural fidelity sub-score and prompt alignment sub-score are both present in telemetry for 100% of verification calls.

## Assumptions

- Amazon Bedrock provides access to a multimodal model capable of accepting both text and image inputs (`amazon.nova-lite-v1:0` by default) for prompt rewriting and verification.
- Amazon Bedrock provides a Stable Diffusion model that supports ControlNet depth or edge conditioning via the standard Bedrock invocation API.
- The AgentCore response body size limit is large enough to accommodate base64-encoded standard image output (e.g., 1024×1024 JPEG); if not, image compression or chunking becomes a follow-on task.
- The worker process that receives `RuntimeInvocationResponse` has write access to the configured storage backend (S3 or R2) using existing credentials.
- The existing worker code handles unknown/extra fields in `RuntimeInvocationResponse` without error (Pydantic v2 default behavior), making `output_image_bytes` a backward-compatible addition.
- `input_image_url` in the request always points to a resource accessible from within the runtime's network context (covered by existing `policy.py` URL allowlist).
