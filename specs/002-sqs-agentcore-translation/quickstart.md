# Quickstart: SQS to AgentCore Translation

## Goal
Implement and verify AgentCore-backed generation processing while preserving existing queue contract and generation lifecycle behavior.

## Prerequisites
- Python virtual environment activated.
- Worker and API dependencies installed.
- Access to PostgreSQL and SQS queue.
- AgentCore runtime ARN and AWS credentials configured.

## Configuration
Set or confirm environment values:
- `SQS_QUEUE_URL`
- `WORKER_CONCURRENCY`, `WORKER_MAX_RETRIES`, `WORKER_VISIBILITY_TIMEOUT`
- `AWS_REGION`, worker AWS credentials for SQS + AgentCore invoke
- AgentCore runtime config (for example runtime ARN env var introduced by implementation)

## Implementation Steps
1. Add generation schema/model/repository support for top-level generated-image-description field(s).
2. Add migration for new generation description column(s).
3. Implement AgentCore provider integration in worker provider factory.
4. Update worker processor to:
   - derive deterministic project-scoped `runtimeSessionId`
   - invoke AgentCore asynchronously
   - persist canonical `output_image_url`
   - persist generated-image description in new top-level field(s)
5. Update consumer logic for:
   - idempotent terminal-status redelivery no-op + delete
   - malformed message dead-letter emission
6. Add OTEL/logging attributes for runtime/session/job IDs and processing outcomes.

## Verification Commands
- Unit tests:
  - `pytest tests/worker -q`
  - `pytest tests/foreman/test_generations_repository.py -q`
- Integration tests (if migration/repository changes are included):
  - `pytest tests/foreman/integration -q`
- Lint/format:
  - `ruff check .`
  - `ruff format .`

## SC-004 Sustained-Run Validation Procedure (30 Minutes)

1. Start worker with AgentCore mode enabled and OTEL export active.
2. Push a steady queue workload for 30 minutes (for example 1 message every 5-10 seconds).
3. Capture the following evidence:
   - consumer poll span count over time (`poll_sqs`)
   - count of completed message deletes
   - count of stalled periods longer than 30 seconds with no poll span
4. Pass criteria:
   - no full-stop consumer stalls during the 30-minute window
   - poll spans continue throughout the run

Suggested command pattern:

```bash
# Producer loop example (replace with project-specific producer)
for i in $(seq 1 360); do
  aws sqs send-message --queue-url "$SQS_QUEUE_URL" --message-body "..." >/dev/null
  sleep 5
done
```

## SC-002 Artifact Accessibility Metric Procedure (99% Threshold)

1. Query completed generations in the target window.
2. For each `output_image_url`, perform a `HEAD`/`GET` check.
3. Compute accessibility ratio:

$$
	ext{accessibility ratio} = \frac{\text{accessible completed artifacts}}{\text{total completed artifacts}}\times 100
$$

4. Pass criteria: ratio >= 99.0%.

Suggested SQL + checker flow:

```bash
psql "$DATABASE_URL" -c "
SELECT id, output_image_url
FROM generations
WHERE status='completed' AND output_image_url IS NOT NULL;
"
```

## Verification Record

Execution date: 2026-05-23

- Targeted unit/integration suite:
  - `pytest tests/worker/test_processor.py tests/worker/test_consumer_extended.py tests/worker/test_providers.py tests/worker/test_agentcore_provider.py tests/foreman/test_generations_repository.py tests/foreman/integration/test_generations_repository.py tests/foreman/integration/test_generations_lifecycle.py tests/foreman/integration/test_migrations.py tests/worker/integration/test_agentcore_iam_boundary.py`
  - Result: 53 passed, 0 failed.
- Changed-file lint check:
  - `ruff check worker/config.py worker/consumer.py worker/main.py worker/processor.py worker/providers/__init__.py worker/providers/agentcore.py foreman/models/generation.py foreman/schemas/generation.py foreman/repositories/postgres_generations_repository.py tests/worker/test_processor.py tests/worker/test_consumer_extended.py tests/worker/test_providers.py tests/worker/test_agentcore_provider.py tests/worker/integration/test_agentcore_iam_boundary.py tests/foreman/test_generations_repository.py tests/foreman/integration/test_generations_repository.py tests/foreman/integration/test_generations_lifecycle.py tests/foreman/integration/test_migrations.py`
  - Result: all checks passed.

## Functional Verification Checklist
- Existing queue payload is accepted unchanged.
- Deterministic project-based `runtimeSessionId` reused across repeated project jobs.
- `runtimeSessionId` length check (>=33) enforced by implementation.
- Completed generations persist canonical `output_image_url`.
- Generated-image description is persisted in top-level generation field(s).
- Malformed messages are emitted to dead-letter handling.
- Redelivered terminal jobs are skipped and message deleted.
- No raw image binaries traverse worker response payloads.
