# Contracts: Worker <-> Queue <-> AgentCore

## 1. Inbound Queue Message Contract (v1 Canonical)
Queue payload remains unchanged.

```json
{
  "generation_id": "f3f52fc8-6739-49e2-a30d-9f1a1e2d8c4a",
  "project_id": "a7c4df21-4de8-4f9a-a72d-60f94f96f437",
  "prompt": "Transform into warm modern interior",
  "input_image_url": "https://cdn.example.com/input.png",
  "created_at": "2026-05-23T10:31:41Z",
  "style_id": "warm-modern",
  "retry_count": 0
}
```

Message attributes:
- `user_id`: string UUID (required for scoped DB state updates).

Validation errors:
- Missing required payload fields => malformed message.
- Malformed messages go to dead-letter flow.

## 2. Derived AgentCore Invoke Contract
`runtimeSessionId` derivation:
- Deterministic from project ID with stable prefix.
- Example: `proj-a7c4df21-4de8-4f9a-a72d-60f94f96f437`
- Minimum length: 33.

Invoke fields (logical):
- `agentRuntimeArn`: configuration-driven runtime selector.
- `runtimeSessionId`: derived as above.
- `payload`: prompt + input image reference only (no worker-side raw image binary relay).

## 3. AgentCore Response Contract (Normalized)
Worker expects a lightweight response with artifact reference and optional generated description text.

```json
{
  "status": "COMPLETED",
  "artifact": {
    "output_image_url": "https://assets.example.com/generations/abc123.png",
    "bucket": "optional-bucket",
    "key": "optional/key.png"
  },
  "generated_image_description": "A warm-toned living room with natural wood and soft lighting"
}
```

Rules:
- `output_image_url` is canonical persisted output location.
- `generated_image_description` persists to top-level generation field(s).
- No raw image bytes in response payload.

## 4. Generation Persistence Contract
On successful completion:
- set `status=completed`
- set canonical `output_image_url`
- set top-level generated-image-description field(s)
- set `processing_time_ms`

On malformed payload:
- emit message to dead-letter flow
- if user scope is available, mark generation failed

On redelivery:
- if generation status in (`completed`, `failed`): no-op and delete message
- else continue standard processing path

## 5. IAM Contract (Least Privilege)
Worker role allowed:
- SQS consume/delete actions for target queue
- `bedrock-agentcore:InvokeAgentRuntime`

Worker role disallowed for output writing:
- `s3:PutObject` (reserved for AgentCore execution role)
