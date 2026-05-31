# Tasks: AgentCore Runtime Configuration

**Input**: Design documents from /specs/003-agentcore-runtime-config/
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Unit and integration test tasks are explicitly included to satisfy constitution test-layer requirements and measurable success criteria.

**Organization**: Tasks are grouped by user story so each story can be implemented and validated independently.

## Format: [ID] [P?] [Story] Description

- [P]: Can run in parallel (different files, no dependencies on incomplete tasks)
- [Story]: Which user story this task belongs to (US1, US2, US3)
- Every task includes exact file path(s)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare runtime configuration and operator documentation baseline.

- [ ] T001 Document AgentCore runtime environment variables in .env.foreman.example
- [ ] T002 Create runtime operations guide in docs/worker/agentcore-runtime.md
- [ ] T003 [P] Add feature implementation overview and dev-only rollout scope notes (FR-008) in specs/003-agentcore-runtime-config/quickstart.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish shared contract enforcement required by all user stories.

**CRITICAL**: No user story implementation should start until this phase is complete.

- [ ] T004 Enforce required user_id message attribute validation in worker/consumer.py
- [ ] T005 Add malformed-message reason normalization for DLQ path in worker/consumer.py
- [ ] T006 Enforce metadata-only runtime response guardrails in worker/providers/agentcore.py
- [ ] T007 Enforce remote worker-accessible output URL validation (FR-011) in worker/providers/agentcore.py
- [ ] T008 Add runtime contract violation logging fields for observability in worker/providers/agentcore.py
- [ ] T009 Update IAM boundary policy documentation with required queue/runtime constraints in docs/worker/agentcore-iam.md
- [ ] T010 Add explicit development-only runtime rollout guardrails and config checks (FR-008) in worker/config.py

**Checkpoint**: Shared queue/runtime contract enforcement is in place.

---

## Phase 3: User Story 1 - Configure Runtime Baseline (Priority: P1) MVP

**Goal**: Ensure worker-to-runtime invocation and response handling follow the agreed img2img contract end-to-end.

**Independent Test**: Publish one valid generation job and confirm worker invokes runtime with contract-compliant request and completes using metadata-only remote URL response.

### Tests for User Story 1

- [ ] T011 [P] [US1] Add/extend unit tests for metadata-only response enforcement and remote output URL handling in tests/worker/test_agentcore_provider.py
- [ ] T012 [P] [US1] Add integration contract test for valid SQS message to runtime completion in tests/worker/integration/test_agentcore_runtime_contract.py

### Implementation for User Story 1

- [ ] T013 [US1] Align AgentCore invocation payload fields with contract (FR-013) in worker/providers/agentcore.py
- [ ] T014 [US1] Align runtime session parameter handling with deterministic project-scoped session IDs in worker/processor.py
- [ ] T015 [P] [US1] Ensure agentcore runtime config fields are complete and documented (FR-001, FR-002) in worker/config.py
- [ ] T016 [US1] Enforce required SQS body fields and required user_id attributes at publish site (FR-014) in foreman/api/v1/endpoints/projects.py
- [ ] T017 [US1] Add canonical request/response examples reflecting remote URL contract in docs/worker/agentcore-runtime.md

**Checkpoint**: User Story 1 is functional and independently verifiable.

---

## Phase 4: User Story 2 - Ensure Safe Runtime Access (Priority: P2)

**Goal**: Ensure runtime access boundaries and denial behavior are explicit, enforced, and auditable.

**Independent Test**: Attempt allowed and disallowed runtime-related actions and confirm documented deny/allow behavior and auditability signals.

### Tests for User Story 2

- [ ] T018 [P] [US2] Add/extend unit tests for contract/policy denial logging in tests/worker/test_agentcore_provider.py
- [ ] T019 [P] [US2] Add integration IAM boundary coverage for allow/deny matrix in tests/worker/integration/test_agentcore_iam_boundary.py

### Implementation for User Story 2

- [ ] T020 [US2] Add explicit worker/runtime allow-deny matrix for runtime integration (FR-004, FR-009) in docs/worker/agentcore-iam.md
- [ ] T021 [US2] Emit structured denial events for contract/policy failures (FR-005) in worker/providers/agentcore.py
- [ ] T022 [P] [US2] Emit ownership-related denial context for missing/invalid user attributes (FR-014) in worker/consumer.py
- [ ] T023 [US2] Propagate runtime access-boundary context to processing telemetry (FR-006) in worker/processor.py
- [ ] T024 [US2] Document security validation workflow for operators in docs/worker/agentcore-runtime.md

**Checkpoint**: User Story 2 is functional and independently verifiable.

---

## Phase 5: User Story 3 - Operate and Recover Runtime (Priority: P3)

**Goal**: Make runtime failure detection and recovery deterministic with fixed retry and DLQ behavior.

**Independent Test**: Simulate runtime failures and verify retry exhaustion, DLQ handling, and recovery runbook steps restore processing.

### Tests for User Story 3

- [ ] T025 [P] [US3] Add/extend unit tests for retry exhaustion and malformed user attribute handling in tests/worker/test_consumer_extended.py
- [ ] T026 [P] [US3] Add integration recovery test for runtime unavailability to manual requeue path in tests/worker/integration/test_agentcore_runtime_recovery.py

### Implementation for User Story 3

- [ ] T027 [US3] Standardize retry-exhaustion reason codes and DLQ context (FR-010) in worker/consumer.py
- [ ] T028 [US3] Add runtime failure span events and attributes for incident detection (FR-006) in worker/processor.py
- [ ] T029 [P] [US3] Ensure worker readiness behavior documents runtime dependency expectations in worker/main.py
- [ ] T030 [US3] Add operational recovery procedure for fixed retry and manual requeue in docs/worker/agentcore-runtime.md
- [ ] T031 [US3] Add incident-response quick checklist for runtime outages in specs/003-agentcore-runtime-config/quickstart.md

**Checkpoint**: User Story 3 is functional and independently verifiable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final consistency, docs cleanup, and end-to-end validation guidance.

- [ ] T032 [P] Reconcile runtime contract wording across docs (FR-011, FR-012, FR-013) in specs/003-agentcore-runtime-config/contracts/worker-agentcore-contract.md
- [ ] T033 Cleanup and type-hint refinements for runtime integration paths in worker/providers/agentcore.py
- [ ] T034 [P] Add SC-002 latency verification assertions to tests/worker/integration/test_agentcore_runtime_contract.py
- [ ] T035 [P] Add SC-003 incident-detection timing verification to tests/worker/integration/test_agentcore_runtime_recovery.py
- [ ] T036 [P] Add SC-005 audit completeness verification in tests/worker/integration/test_agentcore_runtime_contract.py
- [ ] T037 [P] Add final verification command matrix and expected outcomes in specs/003-agentcore-runtime-config/quickstart.md
- [ ] T038 Update feature notes and final implementation status in specs/003-agentcore-runtime-config/plan.md

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1): no dependencies.
- Foundational (Phase 2): depends on Setup; blocks all user stories.
- User Story phases (Phase 3-5): depend on Foundational completion.
- Polish (Phase 6): depends on completion of target user stories.

### User Story Dependencies

- US1 (P1): starts after Phase 2; no dependency on US2/US3.
- US2 (P2): starts after Phase 2; can run in parallel with US1 if staffed.
- US3 (P3): starts after Phase 2; can run in parallel with US1/US2 if staffed.

### Story Completion Order

1. US1 (MVP)
2. US2
3. US3

---

## Parallel Opportunities

### US1

- T012 can run in parallel with T013 and T014 because it is isolated to tests/worker/integration/test_agentcore_runtime_contract.py.
- T015 can run in parallel with T013 and T014 because it is isolated to worker/config.py.

### US2

- T019 can run in parallel with T021 because it is in tests/worker/integration while T021 is implementation in worker/providers/agentcore.py.
- T022 can run in parallel with T021 because it touches worker/consumer.py while T021 focuses on worker/providers/agentcore.py.

### US3

- T026 can run in parallel with T027 and T028 because test implementation is isolated from runtime logic edits.
- T029 can run in parallel with T027 and T028 because it is isolated to worker/main.py.

---

## Parallel Example: User Story 1

```bash
# In parallel after foundational tasks:
Task T011 in tests/worker/test_agentcore_provider.py
Task T013 in worker/providers/agentcore.py
Task T014 in worker/processor.py
Task T015 in worker/config.py
```

## Parallel Example: User Story 2

```bash
# In parallel after foundational tasks:
Task T018 in tests/worker/test_agentcore_provider.py
Task T019 in tests/worker/integration/test_agentcore_iam_boundary.py
Task T021 in worker/providers/agentcore.py
Task T022 in worker/consumer.py
```

## Parallel Example: User Story 3

```bash
# In parallel after foundational tasks:
Task T025 in tests/worker/test_consumer_extended.py
Task T026 in tests/worker/integration/test_agentcore_runtime_recovery.py
Task T027 in worker/consumer.py
Task T028 in worker/processor.py
Task T029 in worker/main.py
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Complete Phase 1 and Phase 2.
2. Complete Phase 3 (US1).
3. Validate queue-to-runtime contract behavior before expanding scope.

### Incremental Delivery

1. Deliver US1 contract-complete runtime baseline.
2. Add US2 runtime access boundaries and denial observability.
3. Add US3 failure-detection and recovery flow hardening.
4. Run Phase 6 polish and finalize operator docs.

### Team Parallel Strategy

1. One developer completes Phase 1-2 baseline.
2. After checkpoint:
   - Developer A: US1 runtime contract implementation.
   - Developer B: US2 access boundary hardening.
   - Developer C: US3 recovery and telemetry tasks.

---

## Notes

- All checklist entries follow required format: checkbox, task ID, optional [P], required [USx] for user-story phases, and explicit file paths.
- Avoid changing queue/runtime contracts outside the files listed in tasks unless required by discovered constraints.
- Commit at logical checkpoints (Foundational complete, each user story complete, polish complete).
