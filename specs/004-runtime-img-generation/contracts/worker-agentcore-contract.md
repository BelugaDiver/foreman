# Worker–AgentCore Contract

**Feature**: 004-runtime-img-generation  
**Files**: `worker/providers/agentcore.py`, `worker/processor.py`  
**Status**: Extension (backward-compatible)

---

## Overview

The worker calls the AgentCore runtime via `AgentCoreProvider.generate()`. The runtime now returns `output_image_bytes` (base64-encoded image) in addition to the existing metadata fields. The worker is responsible for uploading these bytes to storage and writing the resulting URL to the generation record.

---

## `AgentCoreResult` — Extended

```python
@dataclass
class AgentCoreResult:
    output_image_url: str                       # unchanged — placeholder or real URL
    model_used: str                             # unchanged
    generated_image_description: str | None = None  # unchanged
    output_image_bytes: str | None = None       # NEW — base64 image from runtime
```

---

## `AgentCoreProvider.generate()` — Updated Logic

```
1. Invoke runtime → parse RuntimeInvocationResponse
2. If response.output_image_bytes is not None and non-empty:
       a. Decode base64 → raw bytes
       b. Write to temp file (e.g., /tmp/{generation_id}.jpg)
       c. Return AgentCoreResult with output_image_bytes set
          AND output_image_url = placeholder (will be overwritten by processor)
   Else:
       Return AgentCoreResult with output_image_bytes=None and output_image_url from response
```

---

## `JobProcessor.process()` — Updated Branch Logic

The existing processor in `worker/processor.py` already handles two cases:
- `result["output_image_path"]` → upload local file via `_upload_to_storage()`
- `result["output_image_url"]` → use URL directly

The `_run_agent()` method builds this dict. The update adds a third upstream path — writing the decoded bytes to a temp file — so the **existing** `output_image_path` branch handles the upload without any change to `processor.py`.

```python
# In AgentCoreProvider — _run_agent return dict construction:

if agentcore_result.output_image_bytes:
    import base64, tempfile, os
    raw = base64.b64decode(agentcore_result.output_image_bytes)
    tmp = tempfile.NamedTemporaryFile(
        suffix=".jpg", delete=False, prefix=f"{generation_id}_"
    )
    tmp.write(raw)
    tmp.close()
    return {
        "output_image_path": tmp.name,   # processor uploads this and cleans up
        "model_used": agentcore_result.model_used,
        "generated_image_description": agentcore_result.generated_image_description,
    }
else:
    return {
        "output_image_url": agentcore_result.output_image_url,
        "model_used": agentcore_result.model_used,
        "generated_image_description": agentcore_result.generated_image_description,
    }
```

This means **`processor.py` requires zero changes** — the `output_image_path` branch already handles upload + cleanup via `_upload_to_storage()`.

---

## Error Handling Contract

| Scenario | Worker behaviour |
|---|---|
| `output_image_bytes` is `None` | Use `output_image_url` from response (existing fallback path) |
| `output_image_bytes` is present but base64 decode fails | Log error, raise exception (retried by consumer via existing retry logic) |
| Temp file write fails | Log error, raise exception (retried) |
| Storage upload fails | Existing `_upload_to_storage` exception propagates; processor marks generation `failed` |

---

## `_enforce_metadata_only` — Removal

`AgentCoreProvider` currently calls `_enforce_metadata_only()` which raises if the response contains image bytes (it was added to guard against the old text-only contract). This check must be **removed** or **updated** to allow `output_image_bytes`.

```python
# BEFORE (to be removed):
def _enforce_metadata_only(self, normalized: dict) -> None:
    if normalized.get("output_image_bytes"):
        raise ValueError("Runtime returned unexpected image bytes")

# AFTER: remove this method and its call site entirely.
# The worker now explicitly handles output_image_bytes.
```

---

## Sequence Diagram

```
Worker (processor.py)
    │
    ├── _run_agent(job) ──────────────────────────────────────────────►
    │                         AgentCoreProvider.generate()
    │                             │
    │                             ├── _invoke_runtime(payload)
    │                             │       └── boto3 invoke_runtime ──► AgentCore
    │                             │                                         │
    │                             │                              runtime graph.run_graph()
    │                             │                              [Stage 1] rewrite prompt
    │                             │                              [Loop]
    │                             │                                [Stage 2] SD generate
    │                             │                                [Stage 3] verify
    │                             │                              return RuntimeInvocationResponse
    │                             │ ◄──────────────────────────────────────────────────────────
    │                             │
    │                             ├── parse response
    │                             ├── if output_image_bytes:
    │                             │       decode → write temp file
    │                             │       return {output_image_path: "/tmp/..."}
    │                             └── else:
    │                                     return {output_image_url: "https://..."}
    │ ◄──────────────────────────────
    │
    ├── if output_image_path:
    │       _upload_to_storage(path) ──► S3/R2
    │       output_url = download URL
    └── elif output_image_url:
            output_url = url as-is
    │
    └── _update_status(generation_id, "completed", output_image_url=output_url)
```

---

## No Changes Required

| Component | Status |
|---|---|
| `worker/processor.py` | **No changes** — existing `output_image_path` branch handles upload |
| `worker/consumer.py` | **No changes** |
| `worker/config.py` | **No changes** |
| SQS message schema | **No changes** |
| `RuntimeInvocationRequest` | **No changes** |
| Foreman API | **No changes** |
| Database schema | **No changes** |
