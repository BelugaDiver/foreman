# Phase 0 Research: SQS to AgentCore Translation

## Decision 1: Keep existing SQS message contract in v1
- Decision: Preserve existing worker payload shape (`generation_id`, `project_id`, `prompt`, `input_image_url`, `created_at`, optional current fields).
- Rationale: Avoids producer-side migration and aligns with existing `GenerationJob.from_message` validation and user-scope checks.
- Alternatives considered:
  - Introduce `job_id/session_id/source_image_s3_uri` in queue now.
  - Dual-schema parsing for transition.

## Decision 2: Derive AgentCore runtimeSessionId from project_id
- Decision: Compute deterministic project-scoped `runtimeSessionId` with a stable prefix (for example, `proj-<project_id>`), ensuring minimum length >= 33.
- Rationale: Keeps continuity across generations in a project without new mapping persistence complexity.
- Alternatives considered:
  - Persist project->session mapping table.
  - Generate fresh session per generation.

## Decision 3: Canonical artifact storage remains output_image_url
- Decision: Persist final generated artifact using `output_image_url` as the canonical retrievable field.
- Rationale: Matches existing generation read/write patterns and avoids schema churn for bucket/key decomposition in v1.
- Alternatives considered:
  - Store only bucket/key and resolve URL later.
  - Add dedicated artifact columns immediately.

## Decision 4: Idempotent redelivery handling
- Decision: On redelivery, if generation is already terminal (`completed` or `failed`), treat as no-op and delete message.
- Rationale: Prevents duplicate side effects when previous persistence succeeded but message delete failed.
- Alternatives considered:
  - Always reprocess redelivered messages.
  - Never delete and rely solely on visibility timeout/DLQ policy.

## Decision 5: Malformed payload handling via dead-letter flow
- Decision: Malformed inbound jobs are emitted to dead-letter handling. If ownership context exists, corresponding generation should be marked failed.
- Rationale: Avoids poison-message loops and preserves operational visibility.
- Alternatives considered:
  - Immediate delete only.
  - Retry malformed payloads until max retries.

## Decision 6: Store AI generated-image description as top-level generation data
- Decision: Persist generated-image description output on generation top-level field(s), not metadata and not separate table in v1.
- Rationale: Keeps retrieval/query simple and avoids metadata parsing for canonical product behavior.
- Alternatives considered:
  - Store in `metadata` JSONB.
  - Add a separate `outputs_prompt` table.

## Decision 7: Keep worker concurrency model simple
- Decision: Use existing worker-level concurrency only, with no per-project throttling/fairness policy in v1.
- Rationale: Meets feature requirements while minimizing scheduling complexity and rollout risk.
- Alternatives considered:
  - Per-project quota/fairness queueing.
  - Adaptive dynamic concurrency tuning.

## Decision 8: Explicit IAM boundary for AgentCore path
- Decision: Worker role limited to SQS consume/delete + `bedrock-agentcore:InvokeAgentRuntime`; `s3:PutObject` remains only in AgentCore execution role.
- Rationale: Enforces least privilege and aligns with zero-egress architecture intent.
- Alternatives considered:
  - Grant worker direct S3 write as fallback.
  - Shared broad role for worker and runtime.
