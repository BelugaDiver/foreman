# Data Model: SQS to AgentCore Translation

## 1. Translation Job (Queue Payload)
Represents inbound work item consumed by the worker.

Fields (v1 existing contract):
- `generation_id` (string UUID, required)
- `project_id` (string UUID, required)
- `prompt` (string, required, non-empty)
- `input_image_url` (string URL, required)
- `created_at` (RFC3339 timestamp string, required)
- `style_id` (string, optional)
- `retry_count` (integer, optional)
- message attribute: `user_id` (string UUID, optional but required for successful scoped persistence)

Validation rules:
- Missing any required payload field makes message malformed.
- `generation_id` and `project_id` must parse as UUIDs before DB operations.
- `prompt` must be non-empty and non-whitespace.

## 2. Translation Session (Derived Runtime Context)
Project-scoped AgentCore session continuity identifier.

Fields:
- `runtime_session_id` (string, derived)
- `project_id` (UUID source)

Derivation rules:
- Deterministic from `project_id` with stable prefix (for example `proj-<project_id>`).
- Must be at least 33 characters.
- Same `project_id` always yields same `runtime_session_id`.

## 3. Generated Artifact Reference
Result reference returned by AgentCore response and persisted canonically for retrieval.

Fields:
- `output_image_url` (string URL, canonical persisted retrieval location)
- Optional provider details (non-canonical): bucket/key or equivalent resource identifiers.

Validation rules:
- Completion requires non-empty retrievable artifact location.
- Worker result payload must not include raw image bytes.

## 4. Generation Record (Existing DB entity with feature extension)
Core persisted lifecycle record in PostgreSQL `generations` table.

Existing fields used:
- `id` (UUID, maps to `generation_id`)
- `project_id` (UUID)
- `status` (`pending|processing|completed|failed|cancelled`)
- `prompt` (original input prompt)
- `input_image_url` (original input image)
- `output_image_url` (canonical output artifact URL)
- `error_message` (nullable)
- `processing_time_ms` (nullable)

New field(s) for this feature:
- top-level generated-image-description field(s), e.g. `generated_image_description` (nullable text)

Validation rules:
- Top-level description field(s) are canonical location for AI generated-image description output in v1.
- Description output must not be stored canonically in `metadata`.

## 5. Dead-Letter Item (Operational)
Represents malformed/unprocessable inbound message diverted from normal flow.

Fields:
- original message body
- receipt/trace metadata (message ID, receive count)
- failure reason classification

Validation rules:
- Malformed message must be emitted to dead-letter handling.

## Relationships
- One `project_id` has many `generation` records.
- One `project_id` maps deterministically to one `runtime_session_id` in v1.
- Each queue Translation Job targets exactly one Generation Record.

## State Transitions (Generation)
- `pending -> processing -> completed`
- `pending|processing -> failed`
- `pending|processing -> cancelled` (existing API behavior)
- Redelivery rule: if already `completed|failed`, treat as idempotent no-op and delete message.
