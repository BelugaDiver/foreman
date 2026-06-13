# Quickstart: Runtime Image Generation Pipeline

**Feature**: 004-runtime-img-generation  
**Date**: 2026-06-07

---

## Prerequisites

- AWS account with Bedrock access in `us-east-2` (or your target region)
- Bedrock model access granted for:
  - `amazon.nova-lite-v1:0` (prompt rewriting + verification)
  - `us.stability.stable-image-control-structure-v1:0` (depth/structural ControlNet)
  - `us.stability.stable-image-control-sketch-v1:0` (edge ControlNet — optional)
- Existing foreman runtime ZIP deployed or local Python env with `amazon-bedrock-agentcore`, `boto3`, `Pillow`, `httpx`, `pydantic`

---

## 1. Minimal Configuration

Set the following environment variables. All others have working defaults.

```bash
# Required
export RUNTIME_OUTPUT_BASE_URL="https://your-cdn.example.com/generations"
export AWS_DEFAULT_REGION="us-east-2"

# Optional — defaults shown
export PROMPT_REWRITE_MODEL_ID="amazon.nova-lite-v1:0"
export SD_MODEL_ID="us.stability.stable-image-control-structure-v1:0"
export CONTROLNET_MODE="depth"
export VERIFICATION_MAX_ITERATIONS=3
export VERIFICATION_ALIGNMENT_THRESHOLD=0.75
export VERIFICATION_TIME_BUDGET_SECONDS=60
export VERIFICATION_ITER_ESTIMATE_SECONDS=18
export MAX_OUTPUT_IMAGE_BYTES=1048576
export SD_PROMPT_MAX_TOKENS=300
export CORRECTION_CONTEXT_MAX_TOKENS=150
```

---

## 2. Test a Single Invocation (Local)

From the repo root with the virtualenv activated:

```bash
cd runtimes/agentcore_img2img

python -c "
from app.graph import run_graph
import json

result = run_graph(
    generation_id='test-001',
    prompt='Transform this room into a Japandi-style space with warm oak tones and minimalist furniture',
    input_image_url='https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=800',
    style_id=None,
)
print(json.dumps({k: v[:80] + '...' if isinstance(v, str) and len(v) > 80 else v
                  for k, v in result.items()}, indent=2))
"
```

**Expected output:**
```json
{
  "output_image_url": "https://your-cdn.example.com/generations/test-001.png",
  "output_image_bytes": "iVBORw0KGgoAAAANSUhEUgAA...",
  "generated_image_description": "The candidate image achieves strong structural...",
  "model_used": "us.stability.stable-image-control-structure-v1:0"
}
```

---

## 3. Verify the Pipeline Stages

### Check Stage 1 — Prompt Rewriting

```bash
python -c "
from app.stages.rewriter import rewrite_prompt
from app.settings import PipelineSettings
import httpx, base64

settings = PipelineSettings.from_env()
img = httpx.get('https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=400').content
b64 = base64.b64encode(img).decode()

result = rewrite_prompt(
    original_prompt='modern living room',
    image_b64=b64,
    image_format='jpeg',
    settings=settings,
)
print('Enriched prompt:', result.enriched_prompt[:200])
print('Latency ms:', result.latency_ms)
"
```

### Check Stage 2 — SD Generation

```bash
python -c "
from app.stages.generator import generate_image
from app.settings import PipelineSettings
import httpx, base64

settings = PipelineSettings.from_env()
img = httpx.get('https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=400').content
b64 = base64.b64encode(img).decode()

result = generate_image(
    enriched_prompt='A minimalist Japandi living room with warm oak tones, soft linen sofa, and paper lantern pendant light',
    control_image_b64=b64,
    settings=settings,
)
print('finish_reason:', result.finish_reason)
print('image_bytes length:', len(result.image_bytes))
print('Latency ms:', result.latency_ms)
"
```

### Check Stage 3 — Verification

```bash
python -c "
from app.stages.verifier import verify_image
from app.settings import PipelineSettings
import httpx, base64

settings = PipelineSettings.from_env()
ref = httpx.get('https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=400').content
# Reuse reference as candidate for a quick smoke test
b64 = base64.b64encode(ref).decode()

result = verify_image(
    original_prompt='modern living room',
    reference_image_b64=b64,
    candidate_image_b64=b64,
    settings=settings,
)
print('prompt_alignment:', result.prompt_alignment)
print('structural_fidelity:', result.structural_fidelity)
print('composite_score:', result.composite_score)
print('description:', result.description[:120])
"
```

---

## 4. Run the Test Suite

```bash
cd runtimes/agentcore_img2img
pytest tests/ -v --tb=short

# With coverage
pytest tests/ --cov=app --cov-report=term-missing
```

All Bedrock calls are mocked in unit tests via `monkeypatch`. No real AWS credentials required for `pytest`.

---

## 5. Tune the Verification Loop

### Faster / cheaper (fewer iterations)

```bash
export VERIFICATION_MAX_ITERATIONS=1
export VERIFICATION_TIME_BUDGET_SECONDS=25
export VERIFICATION_ITER_ESTIMATE_SECONDS=22
```

Single-pass: generates once, verifies once, returns. No retry budget.

### Quality-first (more retries)

```bash
export VERIFICATION_MAX_ITERATIONS=5
export VERIFICATION_ALIGNMENT_THRESHOLD=0.85
export VERIFICATION_TIME_BUDGET_SECONDS=120
export VERIFICATION_ITER_ESTIMATE_SECONDS=20
```

### Skip verification entirely (not recommended for production)

```bash
export VERIFICATION_MAX_ITERATIONS=1
export VERIFICATION_ALIGNMENT_THRESHOLD=0.0
```

Threshold 0.0 means any score passes. One iteration always exits immediately after the first generation.

---

## 6. Edge ControlNet (Sketch Mode)

To use edge/canny conditioning instead of structural depth:

```bash
export CONTROLNET_MODE="edge"
# SD_MODEL_ID will automatically default to us.stability.stable-image-control-sketch-v1:0
# Or set explicitly:
export SD_MODEL_ID="us.stability.stable-image-control-sketch-v1:0"
```

Edge mode is better for line-art → photorealistic workflows.

---

## 7. Worker Configuration (for `output_image_bytes` upload)

The worker automatically handles `output_image_bytes` when it receives a response from this runtime. No additional worker config is required beyond the existing storage configuration:

```bash
# Existing — no new variables needed
export STORAGE_PROVIDER="s3"        # or "r2"
export S3_BUCKET="your-bucket"
export S3_REGION="us-east-2"
# IAM role or:
export S3_ACCESS_KEY_ID="..."
export S3_SECRET_ACCESS_KEY="..."
```

---

## 8. Verify End-to-End via Worker

1. Publish a generation message to the configured SQS queue (or use the Foreman API to create a generation).
2. Start the worker: `python -m worker.main`
3. Check the generation record — `output_image_url` should be populated with the real S3/R2 URL after the worker uploads the bytes.
4. Check worker logs for `"AgentCore runtime completed"` and `"Uploaded to storage"` events.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `output_image_bytes` is null in response | SD model returned non-null `finish_reason` | Check structured logs for `"SD generation failed"` with `finish_reason` value; often a content filter — adjust prompt |
| Loop exits after 1 iteration with `time_budget_precheck` | `VERIFICATION_TIME_BUDGET_SECONDS` too small relative to `VERIFICATION_ITER_ESTIMATE_SECONDS` | Increase budget or decrease estimate |
| `parse_failed: true` in verification telemetry | Model returned non-JSON output | Check `PROMPT_REWRITE_MODEL_ID`; ensure Nova Lite is accessible; review system prompt |
| `ValueError: input_image_url is required` | Request sent without `input_image_url` | This runtime variant requires an input image; ensure the worker always passes `input_image_url` |
| SD finish_reason `"Filter reason: input image"` | Input image contains filtered content | Pre-screen images before submission |
