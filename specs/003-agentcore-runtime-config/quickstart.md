# Quickstart: AgentCore Runtime Configuration

## 1. Confirm environment and branch
1. Ensure you are on branch 003-agentcore-runtime-config.
2. Confirm feature files are under specs/003-agentcore-runtime-config.

## 2. Configure runtime inputs for worker
1. Set AGENTCORE_RUNTIME_ARN to the target dev runtime.
2. Set AWS_REGION and worker AWS credentials.
3. Keep RUNTIME_SESSION_PREFIX configured (default proj) unless intentionally changed.

## 3. Validate queue-to-worker contract
1. Publish a test SQS message with required body fields:
   - generation_id
   - project_id
   - prompt
   - input_image_url
   - created_at
2. Include user_id as required MessageAttributes entry.
3. Optionally include style_id and retry_count in body.

## 4. Validate runtime request/response contract
1. Run worker processing for an img2img generation.
2. Verify runtime invocation payload includes:
   - prompt
   - generation_id
   - input_image_url (img2img path)
   - optional style_id
   - runtime_session_id as invocation parameter
3. Verify runtime response includes:
   - output_image_url (required)
   - generated_image_description (optional)
   - model_used (optional)
4. Verify response contains no binary_image, image_bytes, or raw_image fields.

## 5. Validate failure and retry behavior
1. Simulate runtime unavailability.
2. Confirm worker retry behavior follows fixed retry limit.
3. Confirm exhausted messages go to DLQ and require manual requeue.

## 6. Validate security boundaries
1. Confirm worker IAM policy includes:
   - sqs:ReceiveMessage
   - sqs:DeleteMessage
   - sqs:ChangeMessageVisibility
   - sqs:SendMessage (DLQ only)
   - bedrock-agentcore:InvokeAgentRuntime
2. Confirm worker IAM policy excludes direct object write actions for generated artifacts.
3. Confirm runtime role excludes SQS consume/delete on worker queue.

## 7. Run verification tests
1. Run worker provider tests focused on AgentCore contract.
2. Run IAM boundary integration test for worker/runtime split.
3. Run affected generation lifecycle tests to ensure queue contract remains compatible.
