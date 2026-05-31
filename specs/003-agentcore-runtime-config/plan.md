# Implementation Plan: AgentCore Runtime Configuration

**Branch**: `003-agentcore-runtime-config` | **Date**: 2026-05-30 | **Spec**: /specs/003-agentcore-runtime-config/spec.md
**Input**: Feature specification from `/specs/003-agentcore-runtime-config/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Configure the AgentCore runtime path for the existing worker so img2img jobs run end-to-end using a strict metadata-only response contract, with worker-owned retry/idempotency/session behavior unchanged. The implementation will formalize queue and runtime contracts, enforce required SQS user_id message attribute handling, preserve least-privilege IAM boundaries, and validate fixed retry-to-DLQ recovery behavior in dev rollout scope.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, boto3 (bedrock-agentcore + sqs), asyncpg via foreman.db, OpenTelemetry, pytest  
**Storage**: PostgreSQL for generation state; object storage URLs (R2/S3-compatible) for image artifacts; SQS for queue transport  
**Testing**: pytest (unit in tests/worker + tests/foreman, integration in tests/foreman/integration and tests/worker/integration)  
**Target Platform**: Linux containerized API + worker services in development environment
**Project Type**: Async backend web-service plus worker process  
**Performance Goals**: Meet SC-002 and SC-003 from spec (>=95% runtime acceptance within 60s in normal ops; detect incidents within 5 minutes)  
**Constraints**: Metadata-only runtime responses; no binary image payloads in worker path; fixed retry limit with DLQ; user_id required in SQS message attributes; dev-only initial rollout  
**Scale/Scope**: One feature slice scoped to worker/runtime contract and runtime configuration behavior for current generation queue flow

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*
*Reference: `.specify/memory/constitution.md`*

- [x] **I. Layered Architecture** — change is concentrated in worker/runtime contract and configuration path; worker continues reusing foreman shared layers.
- [x] **II. Raw SQL** — no ORM or repository layer replacement introduced by this feature.
- [x] **III. Async-First** — runtime and queue calls remain async with existing thread offloading for blocking SDK clients.
- [x] **IV. Event-Driven** — API continues publishing queue messages and worker performs runtime execution asynchronously.
- [x] **V. Protocols** — queue/storage/provider abstractions remain protocol/factory-driven; no direct endpoint coupling to concrete providers.
- [x] **VI. Test Layers** — plan includes unit + integration validation for provider contract, IAM boundary, and lifecycle compatibility.
- [x] **VII. Observability** — runtime session, generation correlation, and failure telemetry remain mandatory in worker path.
- [x] **VIII. Security** — least-privilege IAM split retained; SQS user ownership attribute requirement formalized.

## Project Structure

### Documentation (this feature)

```text
specs/003-agentcore-runtime-config/
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
└── queue/

worker/
├── consumer.py
├── processor.py
├── config.py
└── providers/

tests/
├── foreman/
│   └── integration/
└── worker/
    └── integration/

docs/worker/
```

**Structure Decision**: Use the existing foreman API + worker split. Implement runtime contract/config updates in worker provider/processor and queue contract touchpoints while keeping shared persistence and API layers unchanged.

## Post-Design Constitution Check

- [x] **I. Layered Architecture** — design artifacts preserve foreman/worker layer boundaries.
- [x] **II. Raw SQL** — no ORM introduction; repository contract remains unchanged.
- [x] **III. Async-First** — design keeps async invocation and to_thread wrapping model.
- [x] **IV. Event-Driven** — queue-first processing remains the only generation execution entry.
- [x] **V. Protocols** — runtime integration remains provider/factory mediated.
- [x] **VI. Test Layers** — unit and integration verification paths are captured in quickstart.
- [x] **VII. Observability** — runtime correlation and failure telemetry are explicit in contracts.
- [x] **VIII. Security** — IAM boundary and required SQS user_id attribute are enforced by contract.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations identified.
