# Tasks: SQS to AgentCore Translation

**Input**: Design documents from `/specs/002-sqs-agentcore-translation/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Constitution requires both unit and integration test layers. This task plan includes explicit test tasks per story and cross-cutting verification.

**Organization**: Tasks are grouped by user story to enable independent implementation and validation of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., [US1], [US2], [US3])
- Every task includes an exact file path

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish runtime configuration and documentation scaffolding for AgentCore integration.

- [x] T001 Add AgentCore worker configuration fields (runtime ARN, dead-letter queue URL, session prefix) in `worker/config.py`
- [x] T002 Document new worker environment variables for AgentCore and DLQ in `.env.foreman.example`
- [x] T003 [P] Add feature references and execution notes in `README.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core schema and shared plumbing required before user story implementation.

**⚠️ CRITICAL**: No user story implementation starts before this phase is complete.

- [x] T004 Create migration for top-level generated-image-description field(s) on generations in `migrations/versions/0007_add_generated_image_description_to_generations.py`
- [x] T005 [P] Add generated-image-description field(s) to generation dataclass in `foreman/models/generation.py`
- [x] T006 [P] Add generated-image-description field(s) to generation schemas in `foreman/schemas/generation.py`
- [x] T007 Extend allowed update fields and parsing behavior for new description column(s) in `foreman/repositories/postgres_generations_repository.py`
- [x] T008 Add AgentCore provider selection branch in provider factory in `worker/providers/__init__.py`
- [x] T009 Create AgentCore provider module skeleton (invoke + response normalization contract) in `worker/providers/agentcore.py`
- [x] T010 Add integration migration validation for new generation description column(s) in `tests/foreman/integration/test_migrations.py`

**Checkpoint**: Schema and provider plumbing ready; story implementation can begin.

---

## Phase 3: User Story 1 - Process queued translation jobs (Priority: P1) 🎯 MVP

**Goal**: Process queue jobs end-to-end through AgentCore and persist canonical output URL and generated-image description.

**Independent Test**: Submit a valid queue job and verify generation reaches completed with `output_image_url` and generated-image description fields persisted.

### Implementation for User Story 1

- [x] T011 [US1] Implement AgentCore runtime invocation and payload/response normalization in `worker/providers/agentcore.py`
- [x] T012 [US1] Wire AgentCore provider initialization from worker startup in `worker/main.py`
- [x] T013 [US1] Update worker processor to call AgentCore provider and persist canonical output URL in `worker/processor.py`
- [x] T014 [US1] Persist generated-image-description output to top-level generation field(s) in `worker/processor.py`
- [x] T015 [US1] Update generation status persistence flow for completed/failed outcomes with new field(s) in `worker/processor.py`

### Tests for User Story 1

- [x] T016 [P] [US1] Add worker unit tests for AgentCore success-path persistence in `tests/worker/test_processor.py`
- [x] T017 [P] [US1] Add repository unit tests for generated-image-description update/read behavior in `tests/foreman/test_generations_repository.py`
- [x] T018 [US1] Add integration test for completed generation persistence with output URL and description fields in `tests/foreman/integration/test_generations_repository.py`

**Checkpoint**: Valid jobs complete through AgentCore and persist canonical output + generated description.

---

## Phase 4: User Story 2 - Maintain job state integrity (Priority: P2)

**Goal**: Ensure deterministic project-scoped session continuity and idempotent redelivery behavior.

**Independent Test**: Process repeated jobs for same project and confirm stable session ID; redeliver completed/failed job and verify no-op + message delete.

### Implementation for User Story 2

- [x] T019 [US2] Implement deterministic project-scoped runtimeSessionId derivation (>=33 chars) in `worker/processor.py`
- [x] T020 [US2] Add terminal-status idempotent redelivery guard before expensive processing in `worker/processor.py`
- [x] T021 [US2] Update SQS consumer flow to support idempotent no-op delete behavior in `worker/consumer.py`

### Tests for User Story 2

- [x] T022 [P] [US2] Add worker unit tests for deterministic session derivation in `tests/worker/test_processor.py`
- [x] T023 [P] [US2] Add worker unit tests for terminal redelivery no-op + delete in `tests/worker/test_consumer_extended.py`
- [x] T024 [US2] Add integration test for terminal-state idempotent redelivery behavior in `tests/foreman/integration/test_generations_lifecycle.py`

**Checkpoint**: Session continuity and redelivery idempotency are stable and observable.

---

## Phase 5: User Story 3 - Minimize data transfer risk and cost (Priority: P3)

**Goal**: Enforce metadata-only worker response handling, dead-letter malformed messages, and least-privilege boundaries.

**Independent Test**: Process malformed and valid payloads, verify DLQ behavior, verify no raw image binary relay, and verify worker lacks direct object-write privilege.

### Implementation for User Story 3

- [x] T025 [US3] Implement dead-letter emission path for malformed queue messages in `worker/consumer.py`
- [x] T026 [US3] Add configurable dead-letter queue URL handling in worker startup wiring in `worker/main.py`
- [x] T027 [US3] Enforce metadata-only AgentCore response contract and reject binary relay in `worker/providers/agentcore.py`
- [x] T028 [US3] Document least-privilege IAM policy for worker/runtime split in `docs/worker/agentcore-iam.md`

### Tests for User Story 3

- [x] T029 [P] [US3] Add worker unit tests for malformed-message dead-letter routing in `tests/worker/test_consumer_extended.py`
- [x] T030 [P] [US3] Add worker unit tests for metadata-only response contract enforcement in `tests/worker/test_agentcore_provider.py`
- [x] T031 [US3] Add integration test verifying worker role cannot directly write objects while runtime role can in `tests/worker/integration/test_agentcore_iam_boundary.py`

**Checkpoint**: Malformed jobs are dead-lettered, worker path remains metadata-only, and IAM boundary is enforced.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final hardening, measurable criteria validation, and release-quality verification.

- [x] T032 [P] Add OTEL span/log attributes for runtime session, generation IDs, and error classes in `worker/consumer.py`
- [x] T033 [P] Add OTEL span/log attributes for AgentCore invoke timing/outcomes in `worker/processor.py`
- [x] T034 Add 30-minute sustained-run validation procedure and evidence capture for SC-004 in `specs/002-sqs-agentcore-translation/quickstart.md`
- [x] T035 Add artifact accessibility metric validation procedure (99% threshold) for SC-002 in `specs/002-sqs-agentcore-translation/quickstart.md`
- [ ] T036 Run and record full verification (unit + integration + lint + runtime checks) in `specs/002-sqs-agentcore-translation/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 (US1)**: Depends on Phase 2.
- **Phase 4 (US2)**: Depends on Phase 2 and reuses US1 processor/provider changes.
- **Phase 5 (US3)**: Depends on Phase 2 and builds on consumer/provider flow.
- **Phase 6 (Polish)**: Depends on completion of desired user stories.

### User Story Dependencies

- **US1 (P1)**: MVP; first deliverable.
- **US2 (P2)**: Depends on shared processor/consumer path from US1 but independently testable once implemented.
- **US3 (P3)**: Depends on consumer/provider plumbing from US1 and can be delivered after US2 or in parallel after Phase 2 by separate contributor.

### Within Each User Story

- Implementation before story-level verification.
- Unit tests and integration tests complete before story checkpoint sign-off.
- Story checkpoint must satisfy independent test criteria from spec.

### Parallel Opportunities

- T003 can run in parallel with T001-T002.
- T005 and T006 can run in parallel after T004 is drafted.
- US1 tests T016 and T017 can run in parallel.
- US2 tests T022 and T023 can run in parallel.
- US3 tests T029 and T030 can run in parallel.
- Polish tasks T032 and T033 can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Parallel validation tasks after core US1 implementation
Task: "T016 [US1] Add worker unit tests for AgentCore success-path persistence in tests/worker/test_processor.py"
Task: "T017 [US1] Add repository unit tests for generated-image-description update/read behavior in tests/foreman/test_generations_repository.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 and Phase 2.
2. Complete Phase 3 (US1).
3. Run T016-T018 and validate US1 independently.
4. Demo/deploy MVP slice.

### Incremental Delivery

1. Setup + Foundational
2. US1 (core processing path)
3. US2 (state integrity/idempotency)
4. US3 (dead-letter + metadata-only + IAM boundary)
5. Polish and measurable criteria verification

### Parallel Team Strategy

1. One developer handles schema/repository (T004-T007).
2. One developer handles provider/processor path (T008-T015).
3. One developer handles reliability/security flow (T020-T031).
4. Merge at story checkpoints and run shared verification.

---

## Notes

- [P] marker indicates low-conflict, parallelizable tasks.
- Queue contract remains unchanged in v1.
- Canonical generated-image description storage is top-level generation field(s), not metadata.
- Dead-letter behavior and idempotent redelivery are mandatory acceptance behaviors.
- Unit + integration test layers are required for constitution compliance.
