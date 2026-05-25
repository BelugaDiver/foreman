# Feature Specification: SQS to Agent Translation

**Feature Branch**: `002-sqs-agentcore-translation`  
**Created**: 2026-05-23  
**Status**: Draft  
**Input**: User description: "SQS to AgentCore Img2Img Translation Engine"

## Clarifications

### Session 2026-05-23

- Q: Should canonical job identity use generation_id or switch to job_id/session_id naming? -> A: Keep generation_id as canonical job identity, and manage AgentCore session continuity at the project_id level.
- Q: How should AgentCore runtimeSessionId be managed for project-scoped continuity? -> A: Derive runtimeSessionId deterministically from project_id using a stable namespace prefix (for example, `proj-<project_id>`), and do not persist a separate mapping record.
- Q: Should v1 queue payload add AgentCore-specific fields? -> A: No. Keep the existing worker queue contract unchanged in v1 and use configuration-driven AgentCore runtime selection.
- Q: Where should AgentCore generated-image description output be persisted? -> A: Store generated-image description output directly on the generation record as top-level fields, not in metadata and not in a separate outputs_prompt table.
- Q: What idempotency behavior should apply on redelivery after partial completion? -> A: If generation status is already terminal (`completed` or `failed`), treat redelivery as a no-op and delete the message; otherwise continue normal processing.

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Process queued translation jobs (Priority: P1)

As a platform operator, I want queued image translation jobs to be processed asynchronously so that requests can be completed reliably without blocking the queue consumer.

**Why this priority**: This is the core value of the feature; without end-to-end job processing, no translation request can complete.

**Independent Test**: Submit a valid queued job with a source image location and prompt, then verify the job reaches a completed state with a generated output reference.

**Acceptance Scenarios**:

1. **Given** a new queued translation job with valid input, **When** the worker processes the job, **Then** the system records a completed result containing an output resource reference.
2. **Given** multiple queued translation jobs, **When** processing is active, **Then** jobs continue to be consumed without the queue poller halting on a single in-flight job.

---

### User Story 2 - Maintain job state integrity (Priority: P2)

As an operations engineer, I want each job to map to a consistent processing session and state transition so that retries, traceability, and status reporting remain accurate.

**Why this priority**: Correct state mapping prevents duplicated work and broken job history, which directly affects reliability and supportability.

**Independent Test**: Process a queued job and verify session continuity is preserved from request intake through completion, including job state updates and queue acknowledgment behavior.

**Acceptance Scenarios**:

1. **Given** two queued jobs for the same project, **When** processing is invoked for each, **Then** both invocations use the same project-scoped AgentCore session identifier.
2. **Given** a job that reaches completion, **When** the result is persisted, **Then** the original queue message is acknowledged exactly once.

---

### User Story 3 - Minimize data transfer risk and cost (Priority: P3)

As a security and cost owner, I want generated image binaries to be stored directly in managed object storage so that large payloads do not move through the worker runtime unnecessarily.

**Why this priority**: This reduces operational cost exposure and lowers the attack surface for sensitive binary content.

**Independent Test**: Run a translation job and verify only lightweight metadata returns to the worker while the generated image is written directly to object storage.

**Acceptance Scenarios**:

1. **Given** a completed translation job, **When** the result is returned to the worker, **Then** the payload contains only structured metadata and storage reference fields, not raw image bytes.
2. **Given** a generated output image, **When** the job completes, **Then** the artifact is accessible via the recorded object storage path.

---

### Edge Cases

- A queued message is missing one or more required fields (generation identifier, project identifier, source image location, or prompt).
- The translation runtime returns a malformed or incomplete metadata response that lacks a storage reference.
- Translation exceeds normal completion time and approaches queue visibility limits.
- The output storage write succeeds but state persistence fails, requiring safe retry behavior without duplicate finalization.
- The same message is delivered more than once due to transient infrastructure behavior.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST consume translation jobs from the queue and parse the existing worker payload contract (`generation_id`, `project_id`, `prompt`, `input_image_url`, `created_at`, with existing optional fields) into a validated job request.
- **FR-002**: The system MUST keep `generation_id` as the canonical per-job identifier for worker processing and state updates.
- **FR-003**: The system MUST derive AgentCore `runtimeSessionId` deterministically from `project_id` using a stable namespace prefix so sequential generations for the same project share session context.
- **FR-004**: The system MUST guarantee generated `runtimeSessionId` values are at least 33 characters and valid for AgentCore invocation.
- **FR-005**: The system MUST process translation requests asynchronously using simple worker-level concurrency control; no per-project throttling or fairness policy is required in v1.
- **FR-006**: The system MUST write generated image output directly to managed object storage and return a lightweight response containing an artifact location that can be stored and reliably retrieved from the database using the same URL-style storage pattern as existing generation image fields.
- **FR-007**: The system MUST persist final job state with `output_image_url` as the canonical retrievable artifact location when translation completes successfully.
- **FR-008**: The system MUST acknowledge queue messages only after successful state consolidation. On redelivery, if generation status is already terminal (`completed` or `failed`), processing MUST be treated as an idempotent no-op and the message MUST be deleted.
- **FR-009**: The system MUST handle malformed inbound jobs by emitting them to a dead-letter flow; when ownership context is available, the corresponding generation SHOULD also be marked failed.
- **FR-010**: The system MUST enforce least-privilege access boundaries with explicit worker permissions limited to SQS consume/delete and `bedrock-agentcore:InvokeAgentRuntime`; storage write permissions (`s3:PutObject`) MUST reside only in the AgentCore execution role.
- **FR-011**: The system MUST ensure binary image data is not relayed through worker response payloads.
- **FR-012**: The system MUST support job runtimes up to 5 minutes without duplicate processing caused by queue visibility expiration.
- **FR-013**: The system MUST NOT require new AgentCore-specific fields in the inbound queue payload for v1; AgentCore runtime target selection MUST be controlled by worker configuration.
- **FR-014**: The system MUST persist AgentCore-derived generated-image description output directly on generation top-level fields (for example, `generated_image_description`) so it is queryable without metadata parsing.
- **FR-015**: The system MUST NOT rely on generation `metadata` or a separate `outputs_prompt` table for canonical generated-image description storage in v1.

### Key Entities *(include if feature involves data)*

- **Translation Job**: A queued request using the existing worker contract fields: `generation_id`, `project_id`, `prompt`, `input_image_url`, `created_at`, and optional existing attributes such as `style_id`, `user_id`, and `retry_count`.
- **Translation Session**: A project-scoped continuity context where `runtimeSessionId` is computed as a deterministic namespaced string from `project_id` and reused across multiple generation jobs within the same project.
- **Generated Artifact Reference**: A structured pointer to the final image in object storage, including bucket/container context and object key/path.
- **Job Processing Result**: The normalized completion or failure record written to the system of record, including status, timestamps, artifact reference when available, and top-level generated-image description fields.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 95% of valid translation jobs are processed from queue intake to completed state within 5 minutes.
- **SC-002**: At least 99% of completed jobs store an artifact reference that resolves to an accessible generated image.
- **SC-003**: 100% of worker-to-runtime result payloads for completed jobs contain metadata only and no raw binary image content.
- **SC-004**: During a sustained test window of 30 minutes, queue polling remains active with no observed full-stop consumer stalls caused by in-flight job processing.
- **SC-005**: 100% of AgentCore invocation requests use a deterministic project-scoped `runtimeSessionId` meeting the minimum length requirement and remain stable across repeated generations for the same project.
- **SC-006**: 100% of completed jobs that receive AgentCore generated-image description output persist it in generation top-level description fields (not metadata), retrievable via existing generation read endpoints.

## Assumptions

- A queue, translation runtime, and object storage environment already exist and are available in the target deployment environment.
- Inbound queue payloads follow the documented contract unless explicitly marked as malformed input.
- Database tables and lifecycle states required for job tracking already exist and can be updated by the worker.
- A deterministic `runtimeSessionId` format based on `project_id` (with stable prefixing) is acceptable for security and tenancy boundaries in this deployment.
- A schema migration to add generation generated-image-description field(s) is acceptable within this feature scope.
- This feature scope covers asynchronous translation processing and artifact reference management only; upstream job creation and downstream user-facing retrieval are out of scope.
