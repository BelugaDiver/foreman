# Research: Runtime Image Generation Pipeline

**Feature**: 004-runtime-img-generation  
**Date**: 2026-06-07

---

## R-001: Bedrock Stable Diffusion ControlNet API Format

**Question**: Does AWS Bedrock offer a Stable Diffusion model with ControlNet depth/edge conditioning, and what is the exact invocation format?

### Decision

Use `us.stability.stable-image-control-structure-v1:0` for depth-like structural conditioning (the direct Bedrock equivalent of ControlNet-depth).  
For edge/canny conditioning, use `us.stability.stable-image-control-sketch-v1:0`.

These are the `SD_MODEL_ID` defaults depending on `CONTROLNET_MODE`.

### Rationale

Classic ControlNet does not exist as a separate flag on Bedrock SD models. Stability AI ships ControlNet conditioning as dedicated Image Services model IDs. Control Structure preserves the 3D spatial layout of the input image while regenerating content from the prompt — the correct analogue to ControlNet-depth for photorealistic img2img transforms.

### Alternatives Considered

| Model | Status | Reason rejected |
|---|---|---|
| `stability.stable-diffusion-xl-v1` | Deprecated | AWS: "being deprecated" |
| `stability.sd3-large-v1:0` | Available | No ControlNet param; img2img strength only |
| `stability.stable-image-ultra-v1:1` | Available | No ControlNet param; text-to-image / strength only |
| `us.stability.stable-image-control-sketch-v1:0` | Available | Edge-based; correct for sketch-to-photo, less so for photorealistic depth-preserve |

### Exact Request Body (JSON, `invoke_model`)

```json
{
    "prompt": "<enriched_prompt_string>",
    "image": "<base64_encoded_control_image_string>",
    "control_strength": 0.7,
    "negative_prompt": "blurry, low quality, distorted",
    "seed": 0,
    "output_format": "jpeg"
}
```

- `image` — base64-encoded UTF-8 string of the **control image** (the input image from the request)
- `control_strength` — `[0.0, 1.0]`; default `0.7`; configurable via `SD_CONTROL_STRENGTH`
- `output_format` — `"jpeg"` | `"png"` | `"webp"`; use `jpeg` for size efficiency

### Exact Response Body

```json
{
    "seeds": [2130420379],
    "finish_reasons": [null],
    "images": ["<base64_encoded_output_image_string>"]
}
```

- `images[0]` — base64-encoded output image
- `finish_reasons[0]` — `null` = success; any non-null string = failure (filter or error)
- Runtime must check `finish_reasons[0]` before decoding; non-null = SD stage failure, trigger fallback

### Constraints

| Limit | Value |
|---|---|
| Bedrock `invoke_model` request body | 5 MB |
| Bedrock `invoke_model` response body | 5 MB |
| Input image total pixels | ≤ 9,437,184 (e.g. 3072×3072) |
| Input image aspect ratio | 1:2.5 to 2.5:1 |
| Input image minimum side | 64 px |

The `_resize_image` preprocessing step handles dimension constraints. The `MAX_OUTPUT_IMAGE_BYTES` default (1 MB decoded) is safely within the 5 MB response limit.

---

## R-002: Multimodal Model for Prompt Rewriting and Verification

**Question**: Is Google Gemma available on Bedrock as a multimodal model, and what is the best cheap multimodal model for image+text tasks?

### Decision

Use `amazon.nova-lite-v1:0` as the default `PROMPT_REWRITE_MODEL_ID`.

The original spec defaulted to `google.gemma-3-27b-it-v1:0` — **this model ID does not exist on Bedrock**. Available Gemma variants lack full `invoke_model` image-input documentation.

### Rationale

| Factor | Nova Lite | Gemma 3 12B IT | Claude Haiku |
|---|---|---|---|
| `invoke_model` image format | **Fully documented** | Undocumented for InvokeModel | Documented |
| Cost | Very low | Comparable | Higher |
| Structured JSON output | **Yes** (system prompt) | Yes | Yes |
| Context window | 300K | 128K | 200K |
| Region availability | Wide (cross-region) | Limited (in-region only) | Wide |

### Alternatives Considered

- `google.gemma-3-12b-it` — supports images, but `invoke_model` JSON body format is undocumented in AWS docs; only the OpenAI-compat Chat Completions endpoint has examples. Implementation risk.
- `anthropic.claude-haiku-4-5` — excellent, well-documented, but significantly more expensive than Nova Lite for the rewrite+verify call volume in a pipeline loop.
- `meta.llama3-2-11b-instruct-v1:0` — supports multimodal via flat prompt; structured JSON output less reliable; `max_gen_len` capped at 2048.

### Exact Request Body (`amazon.nova-lite-v1:0` via `invoke_model`)

```json
{
    "schemaVersion": "messages-v1",
    "system": [
        {
            "text": "You are an expert interior and exterior design consultant. Respond ONLY with a JSON object — no markdown, no prose."
        }
    ],
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "image": {
                        "format": "jpeg",
                        "source": {
                            "bytes": "<base64_encoded_image_string>"
                        }
                    }
                },
                {
                    "text": "<user_text_prompt>"
                }
            ]
        }
    ],
    "inferenceConfig": {
        "maxTokens": 512,
        "temperature": 0.7,
        "topP": 0.9
    }
}
```

**Key schema notes:**
- `schemaVersion: "messages-v1"` is **required** for Nova models via `invoke_model`
- `source.bytes` takes a **base64-encoded string** (not binary array — that is for the Converse API only)
- `format` must be one of `jpeg`, `png`, `gif`, `webp`
- Nova Micro does not support image input; always use `nova-lite` or `nova-pro`

### Response Extraction

```python
result = json.loads(response["body"].read())
text_output = result["output"]["message"]["content"][0]["text"]
```

### Structured JSON Output

Reliably enforced via system prompt: `"Respond ONLY with a JSON object — no markdown, no prose."` Combined with an inline schema in the user message (e.g. `Return {"prompt_alignment": <1-10>, "style_fidelity": <1-10>}`), this produces parseable output in >95% of calls. The runtime clamps out-of-range values as a last resort.

---

## R-003: AgentCore Response Body Size Limit

**Question**: What is the AgentCore response body size limit?

### Decision

Apply a `MAX_OUTPUT_IMAGE_BYTES` ceiling of **1 MB (decoded)** before base64 encoding.

### Rationale

The AWS Bedrock `invoke_model` API enforces a **5 MB** synchronous response body limit. AgentCore runtimes return their response payload through the same Bedrock channel, so the effective ceiling is 5 MB for the entire JSON response body (including all fields). Base64 encoding inflates size by ~33%, so a 1 MB decoded image becomes ~1.33 MB base64, leaving ample headroom for the other response fields.

A 1 MB decoded JPEG is approximately a 2048×2048 image at quality 85 — more than sufficient for the `output_image_bytes` use case. The default `MAX_OUTPUT_IMAGE_BYTES = 1048576` is conservative and safe.

---

## R-004: Structured JSON Verification Prompt Format

**Question**: What structured JSON prompt format reliably elicits numeric sub-scores from the verification model?

### Decision

Use a two-part prompt strategy: (1) system instruction enforcing JSON-only output, (2) inline schema in the user message.

### Verification Prompt Structure

**System instruction:**
```
You are an image quality evaluator. Respond ONLY with a valid JSON object — no markdown, no code fences, no prose. Your entire response must be parseable by json.loads().
```

**User message text (appended after the two images):**
```
Evaluate the candidate image (second image) against:
1. The original reference image (first image) — structural/spatial fidelity
2. The original design brief: "<original_prompt>"

Return exactly this JSON:
{"prompt_alignment": <integer 1-10>, "structural_fidelity": <integer 1-10>, "description": "<one sentence explaining the score>"}

10 = perfect match. 1 = no resemblance.
```

### Parsing and Fallback Strategy

```python
import json, re

def parse_verification_response(text: str) -> dict:
    # 1. Direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # 2. Extract JSON object from surrounding text
    match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # 3. Fail-open: treat as accepted
    return {"prompt_alignment": 10, "structural_fidelity": 10, "description": "parse_failed_accept"}

def normalise_score(raw: int | float) -> float:
    """Clamp to [1, 10], normalise to [0, 1]."""
    clamped = max(1.0, min(10.0, float(raw)))
    return (clamped - 1) / 9.0

def composite_score(scores: dict) -> float:
    pa = normalise_score(scores.get("prompt_alignment", 10))
    sf = normalise_score(scores.get("structural_fidelity", 10))
    return (pa + sf) / 2.0
```

### Nova Lite Multi-Image Input (Verification Call)

The verification call passes **two images** (reference + candidate) in a single content array:

```json
{
    "messages": [{
        "role": "user",
        "content": [
            {"image": {"format": "jpeg", "source": {"bytes": "<reference_image_b64>"}}},
            {"image": {"format": "jpeg", "source": {"bytes": "<candidate_image_b64>"}}},
            {"text": "Evaluate the candidate image (second image) against..."}
        ]
    }]
}
```
