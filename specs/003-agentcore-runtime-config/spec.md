# Feature Specification: AgentCore Runtime Host Module

**Feature Branch**: `003-agentcore-runtime-config`  
**Created**: 2026-05-30  
**Status**: Draft  
**Input**: User description: "Configure the actual AgentCore runtime using an agent framework, as its own deployable module, without changing Foreman API or worker behavior."

## Clarifications

### Session 2026-05-30

- Q: What is the runtime graph contract boundary for img2img execution? → A: Worker retains retry/idempotency/session ownership; hosted runtime graph handles img2img pipeline and returns metadata output.
- Q: What output format should the runtime graph return for completed img2img executions? → A: Metadata-only payload to avoid ingress costs, with required output_image_url and optional descriptive guidance fields aligned to current worker expectations.
- Q: Should guidance metadata be required even when current worker processor does not require it? → A: No. Runtime response contract should always match current worker AgentCore expectations.
- Q: What request contract should the runtime accept from the current worker? → A: Required prompt and generation_id, expected input_image_url for img2img, optional style_id, and runtime_session_id passed as an invocation parameter.
- Q: Should user_id be required as an SQS message attribute? → A: Yes. user_id is required as an SQS message attribute.

### Clarification Reapplication To Hosted Runtime

- Runtime host MUST stay compatible with the existing worker request and response contract.
- Runtime host MUST treat tenant/user context as required input for execution authorization decisions.
- Runtime host MUST NOT move retry, idempotency, or queue-recovery responsibilities away from the existing worker.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deploy Runtime Baseline (Priority: P1)

As a platform engineer, I can deploy a standalone AgentCore runtime module so existing Foreman and worker components can invoke it without code changes.

**Why this priority**: Without a deployed runtime host artifact, current worker invocation paths cannot execute in AgentCore.

**Independent Test**: Build and deploy runtime artifact, invoke it with a contract-valid request, and verify metadata-only success response.

**Acceptance Scenarios**:

1. **Given** runtime deployment inputs are missing or invalid, **When** a deployment is attempted, **Then** deployment fails with actionable validation errors.
2. **Given** runtime deployment succeeds, **When** an existing worker-compatible invocation is sent, **Then** runtime accepts it and returns a metadata-only response that matches current worker expectations.

---

### User Story 2 - Enforce Runtime Security Boundaries (Priority: P2)

As a security-conscious operator, I can enforce runtime access boundaries so only approved resources and tenant-scoped requests are processed.

**Why this priority**: Runtime deployment without hard boundaries creates exposure risk even when functional tests pass.

**Independent Test**: Run allow/deny invocation matrix and verify auditable deny events.

**Acceptance Scenarios**:

1. **Given** runtime policy is configured, **When** invocation requests disallowed resources or missing tenant context, **Then** runtime rejects the request and emits auditable denial data.
2. **Given** runtime policy is configured, **When** invocation requests allowed resources with valid tenant context, **Then** runtime executes successfully and emits audit telemetry.

---

### User Story 3 - Operate Runtime Service (Priority: P3)

As an on-call engineer, I can detect runtime host failures and restore service using runtime-focused recovery runbooks.

**Why this priority**: Runtime availability directly affects queue throughput even when Foreman/worker code is unchanged.

**Independent Test**: Simulate runtime unavailability, verify detection and runbook steps, then confirm successful re-invocation.

**Acceptance Scenarios**:

1. **Given** runtime host health degrades, **When** monitoring checks runtime status, **Then** actionable failure signals are raised within the target window.
2. **Given** runtime host recovers, **When** valid invocations are retried by callers, **Then** runtime resumes processing with no contract drift.

---

### Edge Cases

- Invocation arrives with required top-level fields but missing img2img-specific input_image_url.
- Invocation omits runtime_session_id or provides malformed values.
- Invocation omits tenant/user context expected by runtime policy.
- Runtime host returns binary data or non-contract fields that existing worker does not consume.
- Runtime host health endpoint succeeds while downstream model dependency is degraded.
- Runtime deployment is updated while active sessions are in progress.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a standalone AgentCore runtime module that is deployable independently of Foreman API and worker services.
- **FR-002**: Runtime module MUST be deployable to AgentCore using the control plane lifecycle (create/get/list/update/delete) with documented required inputs.
- **FR-003**: Runtime host MUST satisfy AgentCore HTTP runtime contract for hosting: ARM64 container, listening on 0.0.0.0:8080, GET /ping health endpoint, and POST /invocations execution endpoint.
- **FR-004**: Runtime host MUST support the selected agent framework for img2img graph execution while keeping framework internals opaque to callers.
- **FR-005**: Runtime host MUST accept invocation payload contract compatible with current worker expectations: required prompt and generation_id, expected input_image_url for img2img execution, optional style_id, and runtime_session_id as invocation parameter.
- **FR-006**: Runtime host MUST return metadata-only outputs and MUST NOT return binary image content in worker-facing responses.
- **FR-007**: Successful runtime responses MUST include required output_image_url and optional generated_image_description/model_used fields aligned with current worker contract.
- **FR-008**: Runtime host MUST preserve responsibility boundaries by not implementing worker-owned retry/idempotency/queue recovery logic.
- **FR-009**: Runtime host MUST enforce least-privilege access boundaries for model calls, data access, and outbound connectivity.
- **FR-010**: Runtime host MUST require tenant/user context at invocation time and reject requests that do not provide required user context expected by policy.
- **FR-011**: Runtime host MUST emit auditable records for execution attempts, denials, and outcomes correlated by generation_id and runtime session identifiers.
- **FR-012**: Runtime host MUST expose operational health and failure indicators sufficient to support detection within target SLO windows.
- **FR-013**: Initial runtime rollout scope MUST be development environments only.
- **FR-014**: Compatibility assumption MUST remain explicit: upstream caller continues providing user_id from SQS message attributes; runtime host consumes equivalent user context during invocation authorization.

### Key Entities *(include if feature involves data)*

- **Runtime Host Configuration**: Deploy-time/runtime values for container artifact, network mode, execution role, and lifecycle settings.
- **Runtime Invocation Contract**: Request and response schema consumed by the deployed runtime endpoint.
- **Runtime Access Policy**: Allow/deny rules over model access, data resources, outbound calls, and tenant context requirements.
- **Runtime Session Record**: Correlation model for runtime_session_id, generation_id, user context, status, and telemetry.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of invalid runtime deployments are rejected before runtime becomes READY.
- **SC-002**: At least 95% of valid invocations receive runtime acceptance within 60 seconds in normal development operations.
- **SC-003**: Runtime incidents are detectable within 5 minutes of failure onset.
- **SC-004**: 100% of successful invocations return contract-valid metadata-only responses.
- **SC-005**: Audit records are available for 100% of runtime invocations and policy denials within the same business day.

## Assumptions

- Foreman API and worker implementations remain unchanged for this feature.
- Existing queue semantics remain source of truth for upstream user_id requirement.
- Runtime module is deployed and versioned independently from existing service images.
- Existing operational channels are reused with runtime-specific dashboards and alerts added incrementally.
