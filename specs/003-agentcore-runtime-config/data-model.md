# Data Model: AgentCore Runtime Configuration

## Entity: RuntimeConfigurationProfile
- Purpose: Represents deployable runtime configuration and validation state for AgentCore execution.
- Fields:
  - profile_id (string)
  - environment (enum: dev)
  - runtime_arn (string)
  - aws_region (string)
  - runtime_session_prefix (string)
  - response_mode (enum: metadata_only)
  - required_sqs_attributes (set[string], includes user_id)
  - rollout_status (enum: draft, validated, active)
  - created_at (datetime)
  - updated_at (datetime)
- Validation rules:
  - runtime_arn must be non-empty and syntactically valid for AgentCore runtime.
  - response_mode must be metadata_only.
  - required_sqs_attributes must include user_id.

## Entity: RuntimeExecutionSession
- Purpose: Represents a single runtime invocation attempt tied to a generation job.
- Fields:
  - generation_id (UUID)
  - project_id (UUID)
  - runtime_session_id (string)
  - request_payload (object: prompt, generation_id, input_image_url, optional style_id)
  - response_payload (object: output_image_url, optional generated_image_description, optional model_used)
  - status (enum: queued, invoking, completed, failed)
  - failure_reason (string|null)
  - invoked_at (datetime)
  - completed_at (datetime|null)
- Validation rules:
  - request_payload.prompt and request_payload.generation_id required.
  - input_image_url expected for img2img path.
  - response_payload must include output_image_url and must not include binary fields.

## Entity: RuntimeAccessPolicy
- Purpose: Captures allowed runtime actions/resources and deny boundaries.
- Fields:
  - policy_id (string)
  - worker_allowed_actions (set[string])
  - runtime_allowed_actions (set[string])
  - explicit_denies (set[string])
  - policy_source (string)
  - validated_at (datetime)
- Validation rules:
  - worker role includes queue consume/delete and AgentCore invoke.
  - worker role excludes direct object write actions for generated artifacts.
  - runtime role excludes worker queue consume/delete actions.

## Entity: RecoveryPolicy
- Purpose: Defines retry exhaustion behavior and terminal handling for runtime failures.
- Fields:
  - max_retries (int)
  - retry_backoff_strategy (string)
  - exhausted_action (enum: dead_letter_manual_requeue)
  - malformed_message_action (enum: dead_letter_and_delete)
- Validation rules:
  - max_retries must be >= 0.
  - exhausted_action fixed to dead_letter_manual_requeue.

## State Transitions

### RuntimeExecutionSession
- queued -> invoking when worker submits invocation.
- invoking -> completed when metadata-only response includes output_image_url.
- invoking -> failed when invocation errors, contract validation fails, or runtime unavailable.

### RuntimeConfigurationProfile
- draft -> validated after configuration and policy checks pass.
- validated -> active after deployment to dev scope.
- active -> draft if a breaking contract or policy change is introduced.
