# Contract: Worker <> AgentCore Runtime

## 1. SQS Message Contract (API -> Worker)

### Body (required)
- generation_id: string (UUID)
- project_id: string (UUID)
- prompt: string
- input_image_url: string (URL)
- created_at: string (ISO-8601 datetime)

### Body (optional)
- style_id: string | null
- retry_count: integer (default 0)

### MessageAttributes (required)
- user_id: String

### MessageAttributes (optional)
- generation_id: String (currently published for observability; not required by consumer contract)

## 2. Runtime Invocation Contract (Worker -> AgentCore)

### Invocation parameters
- agentRuntimeArn: string (required)
- runtimeSessionId: string (optional, supplied by worker)

### Invocation headers
- None required. `boto3` `invoke_agent_runtime` does not forward custom headers to the container; the runtime is user-agnostic. User context is scoped upstream via `user_id` in the SQS message attributes.

### Payload (required)
- prompt: string
- generation_id: string

### Payload (expected for img2img)
- input_image_url: string

### Payload (optional)
- style_id: string | null

## 3. Runtime Response Contract (AgentCore -> Worker)

### Success payload
- output_image_url: string (required)
- generated_image_description: string | null (optional)
- model_used: string (optional)

### Prohibited fields in worker-facing path
- binary_image
- image_bytes
- raw_image

## 4. Error Contract
- Missing required output_image_url: treated as contract failure.
- Presence of prohibited binary fields: treated as contract failure.
- Invalid or disallowed `input_image_url` host (when allowlist is configured): treated as deny (policy failure).

## 5. Compatibility Notes
- Worker provider supports payload wrapper styles where runtime returns top-level fields or nested under payload/artifact.
- model_used fallback is handled by worker provider path when runtime omits model value.
- Upstream user_id requirement remains anchored in SQS message attributes; the runtime is user-agnostic and does not consume or enforce user context.
