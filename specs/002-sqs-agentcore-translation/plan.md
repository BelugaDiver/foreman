# Implementation Plan: SQS to AgentCore Translation

**Branch**: `002-sqs-agentcore-translation` | **Date**: 2026-05-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-sqs-agentcore-translation/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Replace the current worker-side image generation path with an AgentCore-backed path while preserving
the existing SQS payload contract and generation lifecycle semantics. The worker continues to consume
`generation_id`-based jobs, derives deterministic project-scoped `runtimeSessionId` values,
invokes AgentCore asynchronously, persists canonical artifact location in `output_image_url`, stores
generated-image description output on top-level generation fields, and applies idempotent redelivery
handling (terminal generation => no-op + delete). Malformed messages route to dead-letter handling.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, Pydantic v2, boto3 (`sqs` + `bedrock-agentcore`), OpenTelemetry, asyncpg  
**Storage**: PostgreSQL (generations table), SQS queue, object storage artifact URL persisted in DB  
**Testing**: pytest, pytest-asyncio, unittest.mock/monkeypatch, moto (queue mocks), testcontainers (integration)  
**Target Platform**: Linux containers (API + worker services)
**Project Type**: Event-driven backend service with asynchronous worker  
**Performance Goals**: 95% valid jobs complete within 5 minutes; no queue poller stalls during 30-minute sustained run  
**Constraints**: No binary payload relay through worker responses; deterministic `runtimeSessionId` >= 33 chars; queue contract unchanged in v1; generated-image description stored in top-level generation field(s)  
**Scale/Scope**: Existing Foreman generation pipeline; worker-level configurable concurrency; single feature slice focused on worker and generation persistence

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*
*Reference: `.specify/memory/constitution.md`*

- [x] **I. Layered Architecture** — changes remain in migrations/models/schemas/repositories plus `worker/`; no layer skipping.
- [x] **II. Raw SQL** — repository updates continue through `sql()` and `ALLOWED_UPDATE_FIELDS`; no ORM.
- [x] **III. Async-First** — external SDK calls remain wrapped via `asyncio.to_thread()` where needed.
- [x] **IV. Event-Driven** — SQS-driven worker flow retained; no synchronous API generation execution introduced.
- [x] **V. Protocols** — provider integration remains behind worker provider interface/factory; no endpoint-level concrete coupling.
- [x] **VI. Test Layers** — plan includes unit coverage for worker logic and integration coverage for SQL/migrations.
- [x] **VII. Observability** — OTEL spans/logging will include identifiers and lengths only; no raw prompt/image payload logging.
- [x] **VIII. Security** — user-scoped generation updates retained; explicit least-privilege IAM boundaries included.

Post-Design Re-check: PASS (no constitution violations introduced by data model or interface contracts).

## Project Structure

### Documentation (this feature)

```text
specs/002-sqs-agentcore-translation/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
```text
foreman/
├── api/v1/endpoints/
├── models/
├── repositories/
├── schemas/
└── storage/

worker/
├── consumer.py
├── processor.py
├── config.py
└── providers/

migrations/versions/

tests/
├── foreman/
│   └── integration/
└── worker/
```

**Structure Decision**: Use the existing Foreman single-backend + worker architecture,
adding targeted changes to worker ingestion/processing, generation schema layers,
and migrations with matching tests.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations requiring justification.
