# Phase 0 Research: AgentCore Runtime Configuration

## Decision 1: Keep worker as owner of retry, idempotency, and runtime session identity
- Decision: The worker retains ownership of retry policy, idempotent terminal-state handling, and deterministic runtime session ID derivation.
- Rationale: Existing processing logic already enforces terminal redelivery no-op and fixed retry behavior; moving these controls into runtime would create split ownership and increase failure ambiguity.
- Alternatives considered:
  - Move retry/idempotency into runtime graph: rejected because queue retry semantics are owned by the worker consumer.
  - Hybrid ownership: rejected due to duplicate control planes and harder incident triage.

## Decision 2: Runtime response is metadata-only
- Decision: AgentCore runtime must return metadata-only payloads and never return binary image fields to the worker path.
- Rationale: Current provider explicitly rejects binary fields and the team wants to avoid ingress costs.
- Alternatives considered:
  - Allow binary fallback: rejected due to cost and contract drift.
  - Binary-only responses with worker upload: rejected due to architecture mismatch with current provider enforcement.

## Decision 3: Canonical response contract matches current worker provider expectations
- Decision: Successful runtime responses must include output_image_url; generated_image_description and model_used remain optional.
- Rationale: The current provider normalizes these fields and applies fallback model value behavior in worker/provider code.
- Alternatives considered:
  - Require always-present description and enhancement schema: rejected because current worker contract does not require it.
  - Unstructured runtime payload: rejected because deterministic parsing is needed for reliable updates.

## Decision 4: Runtime invocation payload contract aligns with current worker invocation
- Decision: Runtime invocation payload requires prompt and generation_id, expects input_image_url for img2img, supports optional style_id, and runtime_session_id is supplied as an invocation parameter.
- Rationale: This matches the current worker invocation path and avoids integration churn.
- Alternatives considered:
  - prompt-only payload: rejected because generation correlation and img2img context would be lost.
  - Require style_id always: rejected because style_id is optional in current request flow.

## Decision 5: SQS contract must require user_id as a message attribute
- Decision: user_id is required in SQS MessageAttributes for worker-consumed jobs.
- Rationale: Worker processing path requires user ownership verification and fails without user_id.
- Alternatives considered:
  - user_id optional with fallback lookup: rejected due to additional DB/API coupling and ambiguity.
  - Put user_id in body only: rejected because current publisher/consumer flow reads it from attributes.

## Decision 6: Output URL expectation for runtime-hosted execution
- Decision: Runtime should return a worker-accessible remote output_image_url as the canonical form.
- Rationale: Local file paths imply shared filesystem coupling and are not suitable for runtime-hosted execution boundaries.
- Alternatives considered:
  - Support file:// and remote URLs equally: rejected for runtime environments without shared local storage.
  - file:// only: rejected due to incompatibility with service-isolated deployments.
