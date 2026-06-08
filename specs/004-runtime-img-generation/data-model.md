# Data Model: Runtime Image Generation Pipeline

**Feature**: 004-runtime-img-generation  
**Date**: 2026-06-07

---

## Overview

This feature introduces no new database tables. All entities below are **in-memory runtime structures** — Python dataclasses and Pydantic models used within the runtime process and worker provider for a single invocation lifecycle.

---

## 1. Pipeline Configuration (`settings.py`)

Holds all env-var-driven config. Read at **invocation time** (not import time) to allow dynamic override in tests.

```python
@dataclass
class PipelineSettings:
    # Stage 1 + Stage 3 model
    prompt_rewrite_model_id: str       # PROMPT_REWRITE_MODEL_ID, default: "amazon.nova-lite-v1:0"
    
    # Stage 2 model — maps from CONTROLNET_MODE
    sd_model_id: str                   # SD_MODEL_ID, default: "us.stability.stable-image-control-structure-v1:0"
    sd_control_strength: float         # SD_CONTROL_STRENGTH, default: 0.7
    controlnet_mode: str               # CONTROLNET_MODE ("depth" | "edge"), default: "depth"
    
    # Prompt size controls
    sd_prompt_max_tokens: int          # SD_PROMPT_MAX_TOKENS, default: 300
    correction_context_max_tokens: int # CORRECTION_CONTEXT_MAX_TOKENS, default: 150
    
    # Verification loop controls
    verification_max_iterations: int       # VERIFICATION_MAX_ITERATIONS, default: 3
    verification_alignment_threshold: float # VERIFICATION_ALIGNMENT_THRESHOLD, default: 0.75
    verification_time_budget_seconds: float # VERIFICATION_TIME_BUDGET_SECONDS, default: 60.0
    verification_iter_estimate_seconds: float # VERIFICATION_ITER_ESTIMATE_SECONDS, default: 18.0
    
    # Output size control
    max_output_image_bytes: int        # MAX_OUTPUT_IMAGE_BYTES, default: 1_048_576 (1 MB)
    
    # AWS config
    bedrock_region: str                # AWS_DEFAULT_REGION, default: "us-east-2"
```

**Factory**: `PipelineSettings.from_env()` — reads all env vars with documented defaults; emits `logger.warning` for any var using its default.

---

## 2. Stage Results

### `RewriteResult`

Output of Stage 1 (prompt rewriting).

```python
@dataclass
class RewriteResult:
    enriched_prompt: str      # The full rewritten prompt for SD
    model_id: str             # Model used (for telemetry)
    latency_ms: int           # Wall-clock ms for the Bedrock call
```

**Invariants:**
- `enriched_prompt` is never empty; if the model returns empty/whitespace the original prompt is substituted
- `enriched_prompt` is truncated to `SD_PROMPT_MAX_TOKENS` before passing to Stage 2

---

### `GenerationResult`

Output of Stage 2 (SD + ControlNet generation). Represents one candidate image from a single SD invocation.

```python
@dataclass
class GenerationResult:
    image_bytes: bytes        # Raw decoded image bytes (JPEG)
    image_b64: str            # Base64 string of image_bytes (for verification + response)
    finish_reason: str | None # From SD response; None = success
    seed: int                 # Seed used (for reproducibility / telemetry)
    model_id: str             # Model used (for telemetry)
    latency_ms: int           # Wall-clock ms for the Bedrock call
```

**Invariants:**
- `image_bytes` is non-empty only when `finish_reason is None`
- When `finish_reason` is non-null, `image_bytes` is `b""` and `image_b64` is `""`

---

### `VerificationResult`

Output of Stage 3 (dual-axis composite verification). One verification assessment per candidate image.

```python
@dataclass
class VerificationResult:
    prompt_alignment: int       # Raw sub-score 1–10 from model
    structural_fidelity: int    # Raw sub-score 1–10 from model
    composite_score: float      # 50/50 average normalised to [0, 1]
    description: str            # Human-readable alignment explanation from model
    model_id: str               # Model used (for telemetry)
    latency_ms: int             # Wall-clock ms for the Bedrock call
    parse_failed: bool          # True if JSON parse failed and fail-open was applied
```

**Score formula:**
```
normalise(x) = (clamp(x, 1, 10) - 1) / 9.0
composite_score = (normalise(prompt_alignment) + normalise(structural_fidelity)) / 2.0
```

---

## 3. Verification Loop State

Tracks the best result seen across all iterations. Held in-memory within `run_graph()`.

```python
@dataclass
class LoopState:
    iteration: int                        # Current iteration (1-indexed)
    best_generation: GenerationResult | None  # Best image seen so far
    best_verification: VerificationResult | None  # Score for best_generation
    best_score: float                     # Composite score of best_generation (0.0 if none yet)
    loop_start_time: float                # time.monotonic() at loop entry
    exit_reason: str | None               # Set on exit: "threshold_met" | "time_budget" | 
                                          #               "max_iterations" | "verify_failed" |
                                          #               "time_budget_precheck"
    correction_context: str | None        # Alignment description from last failed verification
```

**Selection rule**: after each iteration, `LoopState.best_*` is updated if `current_score > best_score`.

---

## 4. Pipeline Response

The final output assembled by `run_graph()` and returned to the AgentCore host.

```python
# Maps to RuntimeInvocationResponse fields
{
    "output_image_url": str,               # Placeholder URL (worker fills in real URL after upload)
    "output_image_bytes": str | None,      # base64-encoded output image; None on SD failure
    "generated_image_description": str | None,  # description from last VerificationResult
    "model_used": str,                     # SD model ID used
    # Telemetry fields (extra, ignored by worker if extra="forbid" not set on response)
    "_telemetry": {                        # Not part of RuntimeInvocationResponse schema
        "iterations": int,
        "exit_reason": str,
        "final_composite_score": float,
        "pipeline_latency_ms": int
    }
}
```

> **Note**: Telemetry is emitted via structured logging / OTEL spans, not in the response body. The `_telemetry` block above documents what is logged, not what is returned.

---

## 5. Contract Extension — `RuntimeInvocationResponse`

**File**: `runtimes/agentcore_img2img/app/contracts.py`

```python
class RuntimeInvocationResponse(BaseModel):
    output_image_url: HttpUrl
    generated_image_description: str | None = None
    model_used: str | None = None
    output_image_bytes: str | None = None   # NEW — base64-encoded generated image
```

**Backward compatibility**: the new field is optional with a `None` default. Existing workers that use `extra="forbid"` must be updated (see contracts/).

---

## 6. Worker Provider Extension — `AgentCoreResult`

**File**: `worker/providers/agentcore.py`

```python
@dataclass
class AgentCoreResult:
    output_image_url: str
    model_used: str
    generated_image_description: str | None = None
    output_image_bytes: str | None = None   # NEW — base64 from runtime; None = no image
```

**Worker processing logic** (in `AgentCoreProvider.generate()`):
1. Parse `output_image_bytes` from the runtime response.
2. If present and non-empty: decode from base64 → write to a temp file → set `output_image_path` in the returned dict so the existing `_upload_to_storage` path handles it.
3. If absent or empty: return `output_image_url` from the response unchanged (existing behaviour).

---

## 7. CONTROLNET_MODE to Model ID Mapping

| `CONTROLNET_MODE` value | Effective `SD_MODEL_ID` default |
|---|---|
| `depth` | `us.stability.stable-image-control-structure-v1:0` |
| `edge` | `us.stability.stable-image-control-sketch-v1:0` |

When `SD_MODEL_ID` is set explicitly, it overrides the mode-based default entirely.

---

## 8. State Transitions

```
Invocation received
    │
    ▼
[Pre-checks]
    ├── input_image_url absent → ERROR (reject)
    ├── image fetch fails / invalid format → ERROR (reject)
    └── image resize → proceed
    │
    ▼
[Stage 1: Prompt Rewriting]
    ├── model error → ERROR (no partial result)
    └── empty output → substitute original prompt
    │
    ▼
[Verification Loop — enter]
    │
    ├─ [pre-iteration time check]
    │       └── remaining < iter_estimate → exit (time_budget_precheck)
    │
    ├─ [Stage 2: SD Generation]
    │       ├── model error → SD failure → fallback (description only, no bytes)
    │       └── finish_reason != null → SD failure → fallback
    │
    ├─ [Stage 3: Verification]
    │       ├── model error → fail-open (exit: verify_failed)
    │       └── parse failure → fail-open (exit: verify_failed)
    │
    ├─ score >= threshold → exit (threshold_met)
    ├─ iteration == max_iterations → exit (max_iterations)
    └─ else → update correction_context, increment iteration, loop
    │
    ▼
[Return best result]
```
