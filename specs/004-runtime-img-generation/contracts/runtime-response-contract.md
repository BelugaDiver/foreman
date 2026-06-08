# Runtime Response Contract

**Feature**: 004-runtime-img-generation  
**File**: `runtimes/agentcore_img2img/app/contracts.py`  
**Status**: Extension (backward-compatible)

---

## `RuntimeInvocationRequest` — Unchanged

```python
class RuntimeInvocationRequest(BaseModel):
    prompt: str
    generation_id: str
    input_image_url: HttpUrl | None = None
    style_id: str | None = None
    runtime_session_id: str | None = None
    model_config = ConfigDict(extra="forbid")
```

**No changes.** `input_image_url` was already present; the pipeline treats it as required at the logic layer (not the schema layer) to preserve contract compatibility.

---

## `RuntimeInvocationResponse` — Extended

```python
class RuntimeInvocationResponse(BaseModel):
    output_image_url: HttpUrl                 # unchanged — worker writes real URL after upload
    generated_image_description: str | None = None  # unchanged — now holds final verification description
    model_used: str | None = None             # unchanged — holds SD model ID
    output_image_bytes: str | None = None     # NEW — base64-encoded generated image bytes
    model_config = ConfigDict(extra="ignore") # CHANGED from extra="forbid" to extra="ignore"
```

### Change Notes

| Field | Change | Reason |
|---|---|---|
| `output_image_bytes` | Added, `Optional[str] = None` | Carries base64 output image to worker |
| `model_config` | `extra="forbid"` → `extra="ignore"` | Allows forward-compatible additions (e.g., telemetry fields) without breaking the worker |

### Backward Compatibility

- Workers that previously consumed `RuntimeInvocationResponse` received `output_image_url`, `generated_image_description`, and `model_used`. These fields are unchanged.
- The new `output_image_bytes` field is `None` when image generation fails (fallback path), preserving existing worker behaviour.
- Changing `extra="forbid"` to `extra="ignore"` is backward-compatible: existing serialisation is unchanged; extra fields are silently dropped on parse.

---

## `output_image_bytes` Encoding Spec

| Property | Value |
|---|---|
| Encoding | Base64 (standard alphabet, no line breaks) |
| Image format | JPEG (`output_format: "jpeg"` in SD request) |
| Max decoded size | `MAX_OUTPUT_IMAGE_BYTES` env var, default 1,048,576 bytes (1 MB) |
| When `None` | SD generation failed (all retries exhausted or time budget expired with no successful generation) |

### Encoding Example

```python
import base64

# Encode (runtime side)
output_image_bytes_field = base64.b64encode(image_bytes).decode("utf-8")

# Decode (worker side)
raw_bytes = base64.b64decode(output_image_bytes_field)
```

---

## Validation Rules

| Field | Rule |
|---|---|
| `output_image_url` | Must be a valid HTTP(S) URL; runtime sets a placeholder (e.g., `{RUNTIME_OUTPUT_BASE_URL}/{generation_id}.png`); worker replaces with real storage URL after upload |
| `output_image_bytes` | If non-null, must be a valid base64 string decoding to a non-empty JPEG; runtime validates before returning |
| `generated_image_description` | If non-null, populated from the final verification description; falls back to Stage 1 enriched prompt if verification was skipped |
| `model_used` | Set to the `SD_MODEL_ID` used; never null when generation succeeded |
