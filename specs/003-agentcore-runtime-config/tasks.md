# Tasks: AgentCore Runtime Configuration

**Input**: Design documents from /specs/003-agentcore-runtime-config/
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Unit and integration test tasks are explicitly included to validate runtime-host contract compatibility and deployment behavior.

**Organization**: Tasks are grouped by user story so each story can be implemented and validated independently.

## Format: [ID] [P?] [Story] Description

- [P]: Can run in parallel (different files, no dependencies on incomplete tasks)
- [Story]: Which user story this task belongs to (US1, US2, US3)
- Every task includes exact file path(s)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create standalone runtime module skeleton and baseline deployment docs.

- [X] T001 Create standalone runtime module skeleton in runtimes/agentcore_img2img/
- [X] T002 Add runtime module README with local run and contract notes in runtimes/agentcore_img2img/README.md
- [X] T003 [P] Add dev-only rollout and verification notes (FR-013) in specs/003-agentcore-runtime-config/quickstart.md
- [X] T004 [P] Create runtime operations guide in docs/runtime/agentcore-runtime.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish runtime-host contract and deployment baseline required by all stories.

**CRITICAL**: No user story implementation should start until this phase is complete.

- [X] T005 Implement AgentCore-required host endpoints GET /ping and POST /invocations in runtimes/agentcore_img2img/app/main.py
- [X] T006 Add runtime request schema validation for prompt/generation_id/input_image_url/style_id/runtime_session_id in runtimes/agentcore_img2img/app/contracts.py
- [X] T007 Add runtime response schema enforcing metadata-only output with required output_image_url and optional generated_image_description/model_used in runtimes/agentcore_img2img/app/contracts.py
- [X] T008 Add tenant context enforcement at runtime invocation boundary (derived from caller-provided user context) in runtimes/agentcore_img2img/app/authz.py
- [X] T009 Add runtime observability correlation fields (generation_id, runtime_session_id, user context) in runtimes/agentcore_img2img/app/telemetry.py
- [X] T010 Add ARM64 runtime Dockerfile listening on 0.0.0.0:8080 in runtimes/agentcore_img2img/Dockerfile
- [X] T011 Add AgentCore control-plane deployment config template in runtimes/agentcore_img2img/deployment/runtime-config.example.json
- [X] T012 Document required IAM boundaries for runtime execution and invocation in docs/runtime/agentcore-iam.md

**Checkpoint**: Runtime host contract and deployment foundations are in place.

---

## Phase 3: User Story 1 - Deploy Runtime Baseline (Priority: P1) MVP

**Goal**: Deploy a standalone runtime host artifact that is compatible with existing worker invocation contract.

**Independent Test**: Invoke deployed runtime with contract-valid payload and verify metadata-only contract-valid response.

### Tests for User Story 1

- [X] T013 [P] [US1] Add runtime host unit tests for request validation and response schema enforcement in runtimes/agentcore_img2img/tests/test_contracts.py
- [X] T014 [P] [US1] Add runtime integration test for valid /invocations contract flow in runtimes/agentcore_img2img/tests/integration/test_runtime_contract.py

### Implementation for User Story 1

- [X] T015 [US1] Implement runtime graph adapter using selected framework (Strands-first) in runtimes/agentcore_img2img/app/graph.py
- [X] T016 [US1] Implement invocation handler mapping request payload to graph execution and metadata-only response in runtimes/agentcore_img2img/app/handlers.py
- [X] T017 [P] [US1] Add canonical request/response examples reflecting worker compatibility contract in docs/runtime/agentcore-runtime.md
- [X] T018 [US1] Add runtime deployment script for control plane create/get/list flows in runtimes/agentcore_img2img/deployment/deploy_runtime.py

**Checkpoint**: User Story 1 is functional and independently verifiable.

---

## Phase 4: User Story 2 - Ensure Safe Runtime Access (Priority: P2)

**Goal**: Enforce runtime access boundaries and auditable deny behavior in standalone runtime host.

**Independent Test**: Attempt allowed and disallowed runtime-related actions and confirm documented deny/allow behavior and auditability signals.

### Tests for User Story 2

- [X] T019 [P] [US2] Add runtime unit tests for tenant-context and policy denials in runtimes/agentcore_img2img/tests/test_authz.py
- [X] T020 [P] [US2] Add runtime integration tests for allow/deny matrix in runtimes/agentcore_img2img/tests/integration/test_runtime_iam_boundary.py

### Implementation for User Story 2

- [X] T021 [US2] Implement explicit runtime allow/deny policy checks for model/data/network access in runtimes/agentcore_img2img/app/policy.py
- [X] T022 [US2] Emit structured denial events for policy and tenant-context failures in runtimes/agentcore_img2img/app/telemetry.py
- [X] T023 [US2] Add security validation workflow for operators in docs/runtime/agentcore-runtime.md
- [X] T024 [US2] Document runtime IAM policy matrix and required permissions in docs/runtime/agentcore-iam.md

**Checkpoint**: User Story 2 is functional and independently verifiable.

---

## Phase 5: User Story 3 - Operate and Recover Runtime (Priority: P3)

**Goal**: Make runtime service operations and recovery deterministic without changing worker retry ownership.

**Independent Test**: Simulate runtime host failures and verify detection, health transitions, and recovery runbook steps restore successful invocation behavior.

### Tests for User Story 3

- [X] T025 [P] [US3] Add runtime unit tests for degraded dependency and health signaling in runtimes/agentcore_img2img/tests/test_health.py
- [X] T026 [P] [US3] Add runtime integration recovery tests for temporary unavailability and service restoration in runtimes/agentcore_img2img/tests/integration/test_runtime_recovery.py

### Implementation for User Story 3

- [X] T027 [US3] Implement runtime host health model separating process health and dependency health in runtimes/agentcore_img2img/app/health.py
- [X] T028 [US3] Add runtime failure spans/events and incident-detection telemetry in runtimes/agentcore_img2img/app/telemetry.py
- [X] T029 [P] [US3] Add runtime runbook for outage, rollback, and redeploy flows in docs/runtime/agentcore-runtime.md
- [X] T030 [US3] Add incident-response quick checklist for runtime outages in specs/003-agentcore-runtime-config/quickstart.md

**Checkpoint**: User Story 3 is functional and independently verifiable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final consistency, docs cleanup, and end-to-end validation guidance.

- [X] T031 [P] Reconcile runtime contract wording across docs and examples in specs/003-agentcore-runtime-config/contracts/worker-agentcore-contract.md
- [X] T032 Cleanup and type-hint refinements in runtime host module code under runtimes/agentcore_img2img/app/
- [X] T033 [P] Add SC-002 acceptance-latency verification assertions in runtimes/agentcore_img2img/tests/integration/test_runtime_contract.py
- [X] T034 [P] Add SC-003 incident-detection timing verification in runtimes/agentcore_img2img/tests/integration/test_runtime_recovery.py
- [X] T035 [P] Add SC-005 audit completeness verification in runtimes/agentcore_img2img/tests/integration/test_runtime_contract.py
- [X] T036 [P] Add final verification command matrix and expected outcomes in specs/003-agentcore-runtime-config/quickstart.md
- [X] T037 Update feature notes and final implementation status in specs/003-agentcore-runtime-config/plan.md

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

- T014 can run in parallel with T015 and T016 because it is isolated to integration tests.
- T017 can run in parallel with T015 and T016 because it is documentation-only.

### US2

- T020 can run in parallel with T021 because integration tests are isolated from policy implementation.
- T024 can run in parallel with T021 and T022 because it is documentation-only.

### US3

- T026 can run in parallel with T027 and T028 because tests are isolated from runtime logic edits.
- T029 can run in parallel with T027 and T028 because runbook documentation is isolated from runtime logic.

---

## Parallel Example: User Story 1

```bash
# In parallel after foundational tasks:
Task T013 in runtimes/agentcore_img2img/tests/test_contracts.py
Task T015 in runtimes/agentcore_img2img/app/graph.py
Task T016 in runtimes/agentcore_img2img/app/handlers.py
Task T017 in docs/runtime/agentcore-runtime.md
```

## Parallel Example: User Story 2

```bash
# In parallel after foundational tasks:
Task T019 in runtimes/agentcore_img2img/tests/test_authz.py
Task T020 in runtimes/agentcore_img2img/tests/integration/test_runtime_iam_boundary.py
Task T021 in runtimes/agentcore_img2img/app/policy.py
Task T024 in docs/runtime/agentcore-iam.md
```

## Parallel Example: User Story 3

```bash
# In parallel after foundational tasks:
Task T025 in runtimes/agentcore_img2img/tests/test_health.py
Task T026 in runtimes/agentcore_img2img/tests/integration/test_runtime_recovery.py
Task T027 in runtimes/agentcore_img2img/app/health.py
Task T028 in runtimes/agentcore_img2img/app/telemetry.py
Task T029 in docs/runtime/agentcore-runtime.md
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Complete Phase 1 and Phase 2.
2. Complete Phase 3 (US1).
3. Validate runtime-host contract behavior before expanding scope.

### Incremental Delivery

1. Deliver US1 contract-complete runtime host baseline.
2. Add US2 runtime access boundaries and denial observability.
3. Add US3 runtime operations and recovery hardening.
4. Run Phase 6 polish and finalize operator docs.

### Team Parallel Strategy

1. One developer completes Phase 1-2 runtime host baseline.
2. After checkpoint:
   - Developer A: US1 runtime contract and deployment implementation.
   - Developer B: US2 access boundary hardening.
   - Developer C: US3 operations and telemetry tasks.

---

## Notes

- All checklist entries follow required format: checkbox, task ID, optional [P], required [USx] for user-story phases, and explicit file paths.
- Avoid changing Foreman API and worker files for this feature. Keep scope to runtime host module, contracts, and runtime docs.
- Commit at logical checkpoints (Foundational complete, each user story complete, polish complete).
